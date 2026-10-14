"""Provider adapters. Failures are recorded for the runtime and Settings page."""
import json
import re
import time
import urllib.error
import urllib.request

from . import db, observability, settings

_state = {"last_raw": "", "ping_ts": 0.0, "ping_ok": False, "embed_ts": 0.0, "embed_ok": False,
          "last_error": "", "ping_target": None, "ping_error": ""}


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


def _fill(obj, values: dict):
    """Replace {{placeholders}} inside a JSON structure."""
    if isinstance(obj, str):
        if obj in values and isinstance(values[obj], int):
            return values[obj]
        for k, v in values.items():
            obj = obj.replace(k, str(v))
        return obj
    if isinstance(obj, list):
        return [_fill(x, values) for x in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, values) for k, v in obj.items()}
    return obj


def _dig(data, path: str):
    for part in [p for p in (path or "").split(".") if p != ""]:
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def provider() -> str:
    return settings.get()["provider"]


def single_shot() -> bool:
    """True = one model call per agent (used for hosted platform agents)."""
    s = settings.get()
    return not settings.agentic() and (
        s["agent_mode"] == "single" or (s["agent_mode"] == "auto" and s["provider"] == "custom"))


def enabled_for(agent: str) -> bool:
    """Is this agent allowed to use the AI model? (saves credit; set on the Settings page)"""
    s = settings.get()
    return s["provider"] != "none" and (
        settings.agentic() or agent in (s.get("ai_agents") or []))


def _calls_used() -> int:
    return db.q1("SELECT COUNT(*) n FROM ledger")["n"]


def _dig(data, path: str):
    cur = data
    for part in [p for p in path.split(".") if p]:
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur if isinstance(cur, str) else json.dumps(cur)


def _custom_call(agent: str, system: str, user: str, max_tokens: int, s: dict):
    """Call any HTTP API using the templates from the Settings page."""
    esc = lambda v: json.dumps(str(v))[1:-1]                        # noqa: E731
    agent_id = (s.get("custom_agent_ids") or {}).get(agent, "")
    body = (s["custom_body"].replace("{{system}}", esc(system)).replace("{{user}}", esc(user))
            .replace("{{model}}", esc(s["custom_model"])).replace("{{agent_id}}", esc(agent_id))
            .replace("{{max_tokens}}", str(max_tokens)))
    url = s["custom_url"].replace("{{agent_id}}", agent_id).replace("{{model}}", s["custom_model"])
    headers = {}
    if s["custom_auth_header"]:
        headers[s["custom_auth_header"]] = s["custom_auth_value"].replace("{{key}}", s["custom_key"])
    data = _post(url, json.loads(body), headers, 120)
    if s["custom_path"]:
        try:
            text = _dig(data, s["custom_path"])
        except Exception:
            raise ValueError(f"Response path '{s['custom_path']}' not found. Raw reply: {json.dumps(data)[:300]}")
    else:
        text = json.dumps(data)
    u = data.get("usage", {}) if isinstance(data, dict) else {}
    pt = u.get("prompt_tokens") or u.get("input_tokens") or max(1, (len(system) + len(user)) // 4)
    ct = u.get("completion_tokens") or u.get("output_tokens") or max(1, len(text) // 4)
    return text, pt, ct


def model_name() -> str:
    s = settings.get()
    return {"ollama": s["ollama_model"], "github": s["github_model"],
            "openai": s["openai_model"], "custom": s["custom_model"] or "custom"}.get(s["provider"], "-")


def available() -> bool:
    s = settings.get()
    p = s["provider"]
    if p == "none":
        return False
    if p == "custom":
        return bool(s["custom_url"] and s["custom_key"])
    if p == "github":
        return bool(s["github_token"])
    if p == "openai":
        return bool(s["openai_key"])
    if p == "custom":
        return bool(s["custom_url"])
    target = (s["ollama_url"].rstrip("/"), s["ollama_model"])
    if _state["ping_target"] == target and time.time() - _state["ping_ts"] < 15:
        if not _state["ping_ok"]:
            _state["last_error"] = _state["ping_error"]
        return _state["ping_ok"]
    try:
        with urllib.request.urlopen(target[0] + "/api/tags", timeout=3) as response:
            models = json.loads(response.read()).get("models", [])
        model = s["ollama_model"]
        expected = model if ":" in model else model + ":latest"
        _state["ping_ok"] = any(m.get("name") in (model, expected) for m in models)
        _state["ping_error"] = "" if _state["ping_ok"] else (
            f"Ollama is running, but model '{model}' is not installed. Run: ollama pull {model}")
    except Exception as exc:
        _state["ping_ok"] = False
        _state["ping_error"] = f"Ollama not reachable. Start Ollama or run 'ollama serve'. Details: {exc}"
    _state["ping_target"] = target
    if not _state["ping_ok"]:
        _state["last_error"] = _state["ping_error"]
    _state["ping_ts"] = time.time()
    return _state["ping_ok"]


ollama_available = available            # name used by the agent runtime


def _log_usage(agent, model, pt, ct, start):
    observability.log_llm(agent, model, pt or 0, ct or 0, int((time.time() - start) * 1000))


# ------------------------------- chat --------------------------------------
def chat_json(agent: str, system: str, user: str, max_tokens: int = 350):
    """Ask for ONE JSON object. Returns a dict or None."""
    _state["last_error"] = ""
    if not available():
        _state["last_error"] = _state["last_error"] or "AI provider is not configured or unavailable."
        return None
    s = settings.get()
    if _calls_used() >= int(s["ai_call_budget"]):
        _state["last_error"] = f"AI call budget reached ({s['ai_call_budget']}). Raise it on the Settings page."
        return None
    start = time.time()
    try:
        if s["provider"] == "custom":
            text, pt, ct = _custom_call(agent, system, user, max_tokens, s)
            _state["last_raw"] = text[:400]
            _log_usage(agent, s["custom_model"] or "custom", pt, ct, start)
            return _extract_json(text)
        if s["provider"] == "ollama":
            data = _post(s["ollama_url"].rstrip("/") + "/api/generate", {
                "model": s["ollama_model"], "system": system, "prompt": user,
                "stream": False, "format": "json",
                "options": {"num_predict": max_tokens, "temperature": 0.2}}, timeout=180)
            out = _extract_json(data.get("response"))
            if out is None:
                _state["last_error"] = "Ollama returned invalid JSON. Try a stronger instruction model."
            _log_usage(agent, s["ollama_model"], data.get("prompt_eval_count"),
                       data.get("eval_count"), start)
            return out
        if s["provider"] == "custom":
            headers = {k: str(v).replace("{{key}}", s["custom_key"])
                       for k, v in json.loads(s["custom_headers"] or "{}").items()}
            body = _fill(json.loads(s["custom_body"]), {
                "{{system}}": system, "{{prompt}}": user, "{{model}}": s["custom_model"],
                "{{max_tokens}}": max_tokens})
            data = _post(s["custom_url"], body, headers, 120)
            text = _dig(data, s["custom_path"])
            _log_usage(agent, s["custom_model"] or "custom", 0, 0, start)
            return _extract_json(text if isinstance(text, str) else json.dumps(text))
        base, key, model = _openai_target(s)
        body = {"model": model, "temperature": 0.2, "max_tokens": max_tokens, "stream": False,
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
            detail = exc.read(16384).decode("utf-8", errors="replace")
            for secret_field in ("openai_key", "github_token", "custom_key"):
                secret = s.get(secret_field)
                if secret:
                    detail = detail.replace(secret, "[REDACTED]")
            detail = detail[:4000]
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
    if s["provider"] != "ollama" or not s["embed_model"] or not available():
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
                "tokens, COALESCE(SUM(est_cost),0) cost FROM ledger")
    return {"provider": s["provider"], "model": model_name(), "available": available(),
            "execution_mode": s["execution_mode"],
            "last_error": _state["last_error"], "calls": tot["calls"],
            "tokens": tot["tokens"], "embeddings": embed_available(),
            "budget": int(s["ai_call_budget"]), "est_cost": round(tot["cost"], 4),
            "credit": float(s["credit_usd"]), "single_shot": single_shot()}


def test() -> dict:
    _state["last_error"] = ""
    _state["ping_ts"] = 0.0
    if provider() == "none":
        if settings.agentic():
            return {"ok": False, "message": "Agentic execution requires an AI provider. Connect one in Settings."}
        return {"ok": True, "message": "No AI model selected. The platform runs on "
                "rules + retrieval + templates."}
    if not available():
        return {"ok": False, "message": _state["last_error"] or "Not configured yet."}
    _state["last_raw"] = ""
    out = chat_json("TEST", 'Reply with exactly this JSON: {"ok": true, "word": "ready"}',
                    "Say ready.", 60)
    if out:
        return {"ok": True, "message": f"Connected to {provider()} / {model_name()}."}
    if _state["last_raw"]:
        return {"ok": False, "message": "The API answered, but not with JSON. Raw reply: " + _state["last_raw"]
                + "  (Fix the response path, or tighten the agent instructions to reply in JSON.)"}
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
