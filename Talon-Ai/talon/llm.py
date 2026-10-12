"""One door to every AI engine:  none | Ollama (local) | GitHub Models | any OpenAI-compatible API.
All functions are safe: on any problem they return None and remember the error
(shown on the Settings page). Agents then fall back to their rule-based answers."""
import json
import re
import time
import urllib.error
import urllib.request

from . import db, observability, settings

_state = {"ping_ts": 0.0, "ping_ok": False, "embed_ts": 0.0, "embed_ok": False,
          "last_error": ""}


# ------------------------------- plumbing ----------------------------------
def _post(url: str, payload: dict, headers: dict = None, timeout: int = 120):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _openai_target(s: dict):
    if s["provider"] == "github":
        return ("https://models.github.ai/inference", s["github_token"], s["github_model"])
    return (s["openai_base"].rstrip("/"), s["openai_key"], s["openai_model"])


def _extract_json(text: str):
    text = (text or "").strip()
    try:
        out = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            out = json.loads(m.group(0))
        except Exception:
            return None
    return out if isinstance(out, dict) else None


def provider() -> str:
    return settings.get()["provider"]


def model_name() -> str:
    s = settings.get()
    return {"ollama": s["ollama_model"], "github": s["github_model"],
            "openai": s["openai_model"]}.get(s["provider"], "-")


def available() -> bool:
    s = settings.get()
    p = s["provider"]
    if p == "none":
        return False
    if p == "github":
        return bool(s["github_token"])
    if p == "openai":
        return bool(s["openai_key"])
    if time.time() - _state["ping_ts"] < 15:                  # ollama: cached ping
        return _state["ping_ok"]
    try:
        with urllib.request.urlopen(s["ollama_url"] + "/api/tags", timeout=1.5):
            _state["ping_ok"] = True
    except Exception as exc:
        _state["ping_ok"] = False
        _state["last_error"] = f"Ollama not reachable: {exc}"
    _state["ping_ts"] = time.time()
    return _state["ping_ok"]


ollama_available = available            # name used by the agent runtime


def _log_usage(agent, model, pt, ct, start):
    observability.log_llm(agent, model, pt or 0, ct or 0, int((time.time() - start) * 1000))


# ------------------------------- chat --------------------------------------
def chat_json(agent: str, system: str, user: str, max_tokens: int = 350):
    """Ask for ONE JSON object. Returns a dict or None."""
    if not available():
        return None
    s = settings.get()
    start = time.time()
    try:
        if s["provider"] == "ollama":
            data = _post(s["ollama_url"] + "/api/generate", {
                "model": s["ollama_model"], "system": system, "prompt": user,
                "stream": False, "format": "json",
                "options": {"num_predict": max_tokens, "temperature": 0.2}}, timeout=180)
            out = _extract_json(data.get("response"))
            _log_usage(agent, s["ollama_model"], data.get("prompt_eval_count"),
                       data.get("eval_count"), start)
            return out
        base, key, model = _openai_target(s)
        body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        headers = {"Authorization": "Bearer " + key}
        json_mode, data = True, None
        for attempt in range(4):
            try:
                payload = dict(body, response_format={"type": "json_object"}) if json_mode else body
                data = _post(base + "/chat/completions", payload, headers, 90)
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 400 and json_mode:                 # model has no JSON mode
                    json_mode = False
                    continue
                if exc.code == 429 and attempt < 3:               # rate limited: wait, retry
                    wait = int(exc.headers.get("Retry-After", "5") or 5)
                    _state["last_error"] = f"Rate limited, waiting {min(wait, 20)}s"
                    time.sleep(min(wait, 20))
                    continue
                raise
        if data is None:
            return None
        u = data.get("usage", {})
        _log_usage(agent, model, u.get("prompt_tokens"), u.get("completion_tokens"), start)
        return _extract_json(data["choices"][0]["message"]["content"])
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode()[:200]
        except Exception:
            pass
        _state["last_error"] = f"HTTP {exc.code} from {s['provider']}: {detail}"
    except Exception as exc:
        _state["last_error"] = f"{type(exc).__name__}: {exc}"
    return None


# ------------------------------- embeddings --------------------------------
def embed_available() -> bool:
    """Embeddings are used only with Ollama (free, local). Other engines use the
    built-in hashing embedder so free API quotas are not spent on indexing."""
    s = settings.get()
    if s["provider"] != "ollama" or not available():
        return False
    if time.time() - _state["embed_ts"] < 30:
        return _state["embed_ok"]
    _state["embed_ok"] = embed(["ping"]) is not None
    _state["embed_ts"] = time.time()
    return _state["embed_ok"]


def embed(texts: list):
    s = settings.get()
    if s["provider"] != "ollama" or not available():
        return None
    try:
        data = _post(s["ollama_url"] + "/api/embed",
                     {"model": s["embed_model"], "input": texts}, timeout=120)
        vecs = data.get("embeddings")
        return vecs if vecs and len(vecs) == len(texts) else None
    except Exception as exc:
        _state["last_error"] = f"Embedding model problem: {exc}"
        return None


# ------------------------------- status / test -----------------------------
def status() -> dict:
    s = settings.get()
    tot = db.q1("SELECT COUNT(*) calls, COALESCE(SUM(prompt_tokens+completion_tokens),0) "
                "tokens FROM ledger")
    return {"provider": s["provider"], "model": model_name(), "available": available(),
            "last_error": _state["last_error"], "calls": tot["calls"],
            "tokens": tot["tokens"], "embeddings": embed_available()}


def test() -> dict:
    _state["last_error"] = ""
    _state["ping_ts"] = 0.0
    if provider() == "none":
        return {"ok": True, "message": "No AI model selected. The platform runs on "
                "rules + retrieval + templates."}
    if not available():
        return {"ok": False, "message": _state["last_error"] or "Not configured yet."}
    out = chat_json("TEST", 'Reply with exactly this JSON: {"ok": true, "word": "ready"}',
                    "Say ready.", 40)
    if out:
        return {"ok": True, "message": f"Connected to {provider()} / {model_name()}."}
    return {"ok": False, "message": _state["last_error"] or "No valid answer from the model."}


def list_github_models() -> list:
    s = settings.get()
    if not s["github_token"]:
        return []
    try:
        req = urllib.request.Request("https://models.github.ai/catalog/models", headers={
            "Authorization": "Bearer " + s["github_token"],
            "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return sorted(m.get("id", "") for m in data if m.get("id"))
    except Exception as exc:
        _state["last_error"] = f"Could not list GitHub models: {exc}"
        return []
