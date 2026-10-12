"""User settings (AI engine choice etc.), saved in data/settings.json.
Environment variables override the file."""
import json
import os
import threading

from . import config

_lock = threading.Lock()
DEFAULTS = {
    "provider": "none",            # none | ollama | github | openai
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:7b",
    "embed_model": "nomic-embed-text",
    "github_token": "",
    "github_model": "openai/gpt-4.1-mini",
    "openai_base": "https://api.groq.com/openai/v1",
    "openai_key": "",
    "openai_model": "llama-3.1-8b-instant",
    "demo_pace": 0.5,              # seconds of "thinking" shown per agent when no AI model is used
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
    if os.getenv("TALON_USE_LLM", "").lower() == "off":
        out["provider"] = "none"
    elif os.getenv("TALON_LLM_PROVIDER"):
        out["provider"] = os.getenv("TALON_LLM_PROVIDER").lower()
    return out


def save(new: dict) -> dict:
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
    for k in ("github_token", "openai_key"):
        s[k] = "********" if s[k] else ""
    return s
