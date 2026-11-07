"""Provider abstraction: switching LLM vendor is one line in settings.yaml (llm.provider)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def generate_json(self, system: str, prompt: str) -> dict[str, Any]:
        """Return the model's answer parsed as a JSON object, or raise LLMError."""


def get_provider(cfg) -> LLMProvider | None:
    name = (cfg.s("llm", "provider") or "none").lower()
    if name == "none":
        return None
    if name == "gemini":
        from .gemini import Gemini
        if not cfg.secrets.gemini:
            return None
        return Gemini(cfg.secrets.gemini, cfg.s("llm", "models") or [],
                      temperature=float(cfg.s("llm", "temperature", default=0.4)),
                      retries=int(cfg.s("llm", "max_retries", default=4)),
                      timeout=float(cfg.s("llm", "timeout_seconds", default=60)))
    raise LLMError(f"unknown llm provider: {name}")


def cached_generate(provider: LLMProvider, state, system: str, prompt: str) -> dict[str, Any]:
    """Identical inputs (e.g. a re-run after a failed send) do not cost a second call."""
    key = hashlib.sha1((system + "\x00" + prompt).encode()).hexdigest()
    cache = state.cache("llm")
    if key in cache:
        return cache[key]["out"]
    out = provider.generate_json(system, prompt)
    cache[key] = {"out": out}
    if len(cache) > 40:                    # keep the newest 40
        for k in list(cache)[: len(cache) - 40]:
            cache.pop(k)
    state.set_cache("llm", cache)
    return out


def parse_json_text(text: str) -> dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end < 0:
        raise LLMError("model did not return JSON")
    try:
        return json.loads(t[start:end + 1])
    except ValueError as exc:
        raise LLMError(f"bad JSON from model: {exc}") from exc
