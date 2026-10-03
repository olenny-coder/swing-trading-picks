"""Groq chat-completions client (OpenAI-compatible) for the LLM research agent.

Groq's free plan is rate limited per minute **and** per day, and the binding
limit for a small model is usually tokens-per-minute. So this client:

- sends compact prompts (the caller keeps the brief short),
- asks for a JSON object (``response_format``) so the reply is machine-readable,
- retries 429 / 5xx with backoff, honouring ``Retry-After`` when Groq sends it.

The model's reply is **untrusted input**: callers must validate it against a
strict schema (see ``services/research_service.py``) and must never execute or
act on free-form instructions from it.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
# Confirmed on Groq's free plan (30 RPM / 1K RPD / 8K TPM / 200K TPD).
DEFAULT_MODEL = "openai/gpt-oss-120b"
FALLBACK_MODELS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
)

_RETRY_STATUSES = {429, 500, 502, 503, 504}


class GroqError(RuntimeError):
    """Raised when Groq cannot be reached or returns an error response."""


@dataclass
class GroqCompletion:
    """A parsed JSON completion plus the metadata we store for auditability."""

    data: dict
    model: str
    usage: dict = field(default_factory=dict)


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 45.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise GroqError("No Groq API key configured")
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))

    # -- internals ---------------------------------------------------------
    def _post(self, payload: dict) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:  # network/timeout
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self._backoff(attempt))
                continue

            if resp.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                time.sleep(self._retry_after(resp) or self._backoff(attempt))
                continue
            return resp

        raise GroqError(f"Groq request failed: {last_error}") from last_error

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(8.0, 2.0 * (2**attempt))

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        raw = resp.headers.get("retry-after")
        if not raw:
            return None
        try:
            return min(30.0, max(0.0, float(raw)))
        except ValueError:
            return None

    # -- public API --------------------------------------------------------
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> GroqCompletion:
        """Run one JSON-mode completion and return the parsed object."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = self._post(payload)

        if resp.status_code >= 400:
            detail = resp.text[:300]
            try:
                body = resp.json()
                detail = str(body.get("error", {}).get("message") or body)[:300]
            except ValueError:
                pass
            raise GroqError(f"Groq HTTP {resp.status_code}: {detail}")

        try:
            body = resp.json()
        except ValueError as exc:
            raise GroqError("Groq returned a non-JSON response") from exc

        choices = body.get("choices") or []
        if not choices:
            raise GroqError("Groq returned no choices")
        content = (choices[0].get("message") or {}).get("content") or ""

        try:
            data = json.loads(content)
        except ValueError as exc:
            raise GroqError(f"Groq reply was not valid JSON: {content[:200]}") from exc
        if not isinstance(data, dict):
            raise GroqError("Groq reply was not a JSON object")

        return GroqCompletion(
            data=data,
            model=body.get("model") or self.model,
            usage=body.get("usage") or {},
        )

    def test_connection(self) -> tuple[bool, str, dict]:
        """Small round-trip used by the Settings 'Test' button."""
        try:
            out = self.complete_json(
                system="Reply with JSON only.",
                user='Return exactly {"ok": true} as JSON.',
                max_tokens=32,
            )
        except GroqError as exc:
            return False, str(exc), {}
        return True, f"Groq reachable (model {out.model})", {"model": out.model}
