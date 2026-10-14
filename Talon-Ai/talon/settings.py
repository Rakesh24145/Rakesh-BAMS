"""User settings (AI engine choice etc.), saved in data/settings.json.
Environment variables override the file."""
import json
import os
import threading

from . import config

_lock = threading.Lock()
DEFAULTS = {
    "execution_mode": "agentic",   # agentic (AI required) | legacy (explicit rules fallback)
    "provider": "none",            # none | ollama | github | openai
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:3b",
    "embed_model": "nomic-embed-text",
    "github_token": "",
    "github_model": "openai/gpt-4.1-mini",
    "openai_base": "https://api.groq.com/openai/v1",
    "openai_key": "",
    "openai_model": "llama-3.1-8b-instant",
    "mode": "lite",                # lite = 4 agents (demo)   |   full = 10 agents (needs restart)
    "custom_url": "",              # any other AI endpoint (see the guide)
    "custom_key": "",
    "custom_model": "",
    "custom_headers": '{"Authorization": "Bearer {{key}}"}',
    "custom_body": '{"model": "{{model}}", "messages": [{"role": "system", "content": "{{system}}"}, {"role": "user", "content": "{{prompt}}"}], "max_tokens": "{{max_tokens}}"}',
    "custom_path": "choices.0.message.content",
    "demo_pace": 0.5,
    # --- which parts use the AI model, and spending limits (protects a small credit) ---
    "agent_mode": "auto",          # auto | loop | single   (single = one call per agent)
    "ai_agents": ["ORIGIN", "ATHENA", "NORTHSTAR", "OMNIVIEW", "ASK_TALON"],
    "ai_call_budget": 150,         # stop calling the model after this many calls
    "credit_usd": 4.0,             # your credit, shown next to the estimated spend
    "price_per_1k": 0.002,         # USD per 1,000 tokens (look it up for your model)
    # --- "custom" provider: Capgemini Generative Engine or any other HTTP API ---
    "custom_url": "",
    "custom_auth_header": "Authorization",
    "custom_auth_value": "Bearer {{key}}",
    "custom_key": "",
    "custom_model": "",
    "custom_body": '{"model": "{{model}}", "messages": [{"role": "system", "content": "{{system}}"}, {"role": "user", "content": "{{user}}"}], "temperature": 0.2, "max_tokens": {{max_tokens}}}',
    "custom_path": "choices.0.message.content",
    "custom_agent_ids": {},              # seconds of "thinking" shown per agent when no AI model is used
}
_cache: dict = {}


def _path():
    return config.DATA_DIR / "settings.json"


def get() -> dict:
    with _lock:
        if not _cache:
            data = dict(DEFAULTS)
            try:
                data.update(json.loads(_path().read_text(encoding="utf-8")))
            except Exception:
                pass
            _cache.update(data)
        out = dict(_cache)
    token = os.getenv("GITHUB_TOKEN") or os.getenv("TALON_GITHUB_TOKEN")
    if token and not out["github_token"]:
        out["github_token"] = token
    if os.getenv("TALON_MODE"):
        out["mode"] = os.getenv("TALON_MODE").lower()
    if os.getenv("TALON_CUSTOM_KEY") and not out["custom_key"]:
        out["custom_key"] = os.getenv("TALON_CUSTOM_KEY")
    if os.getenv("TALON_USE_LLM", "").lower() == "off":
        out["provider"] = "none"
    elif os.getenv("TALON_LLM_PROVIDER"):
        out["provider"] = os.getenv("TALON_LLM_PROVIDER").lower()
    return out


def agentic() -> bool:
    return get()["execution_mode"] == "agentic"


def save(new: dict) -> dict:
    if "execution_mode" in new and new["execution_mode"] not in ("agentic", "legacy"):
        raise ValueError("Execution mode must be agentic or legacy")
    with _lock:
        current = dict(DEFAULTS)
        current.update(_cache or {})
        for k, v in new.items():
            if k in DEFAULTS:
                if k.endswith(("token", "key")) and v in ("", None, "********"):
                    continue                          # keep the stored secret
                current[k] = v
        _cache.clear()
        _cache.update(current)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(current, indent=2), encoding="utf-8")
    return public()


def public() -> dict:
    s = get()
    for k in ("github_token", "openai_key", "custom_key"):
        s[k] = "********" if s[k] else ""
    return s
