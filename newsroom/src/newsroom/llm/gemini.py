"""Google Gemini via the REST API (Google AI Studio free tier). No SDK: fewer moving parts."""
from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

from .base import LLMError, parse_json_text

log = logging.getLogger(__name__)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class Gemini:
    name = "gemini"

    def __init__(self, key: str, models: list[str], temperature: float = 0.4, retries: int = 4,
                 timeout: float = 60):
        self.key, self.models = key, models or ["gemini-flash-latest"]
        self.temperature, self.retries, self.timeout = temperature, retries, timeout
        self.used_model: str | None = None

    def generate_json(self, system: str, prompt: str) -> dict[str, Any]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": self.temperature, "responseMimeType": "application/json"},
        }
        errors = []
        for model in self.models:
            try:
                out = self._call(model, body)
                self.used_model = model
                return out
            except LLMError as exc:
                log.warning("gemini %s: %s", model, exc)
                errors.append(f"{model}: {exc}")
        raise LLMError("; ".join(errors))

    def _call(self, model: str, body: dict) -> dict[str, Any]:
        headers = {"x-goog-api-key": self.key, "Content-Type": "application/json"}
        for attempt in range(self.retries + 1):
            try:
                r = requests.post(URL.format(model=model), json=body, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                err: str = type(exc).__name__
            else:
                if r.status_code == 200:
                    return _extract(r.json())
                if r.status_code in (400, 401, 403, 404):
                    # wrong model name / retired model / bad key: retrying will not help
                    raise LLMError(f"HTTP {r.status_code}")
                err = f"HTTP {r.status_code}"
            if attempt < self.retries:
                time.sleep(min(2 * 2 ** attempt, 30) + random.uniform(0, 1))   # 429 / 5xx backoff
        raise LLMError(err)


def _extract(d: dict) -> dict[str, Any]:
    try:
        parts = d["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError) as exc:
        reason = (d.get("promptFeedback") or {}).get("blockReason") or "empty answer"
        raise LLMError(str(reason)) from exc
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return parse_json_text(text)
