"""The only place that calls Gemini (CLAUDE.md, ARCHITECTURE.md section 3).

- Model calls: interactions.create(model, input, generation_config {"thinking_level"}).
  Plain text on the stable client; structured output (response_format=<JSON schema>,
  response_mime_type JSON) on the v1beta client: the stable API rejects those fields.
- Decisions API: v1beta client, decisions.create.
- Never temperature / top_p / top_k / a thinking budget / "minimal".
- One retry on 429 / 5xx after 2 s. Logs role, seconds and token counts only:
  never prompt or reply content, never the key.
Tests replace the instance with a fake via set_models().
"""

from __future__ import annotations

import json
import logging
import time

from app.config import get_settings

log = logging.getLogger("interlock.models")

ROLE_MODEL = {
    "understand": "MODEL_NEON",
    "long_read": "MODEL_ARGON",
    "values": "MODEL_ARGON",
    "explain": "MODEL_CARBON",
    "headlines": "MODEL_HYDROGEN",
}
RETRY_CODES = {429, 500, 502, 503, 504}
RETRY_WAIT_S = 2
CALL_TIMEOUT_S = 180


def _code(e: Exception) -> int | None:
    for attr in ("code", "status_code", "status"):
        v = getattr(e, attr, None)
        if isinstance(v, int):
            return v
    return None


class Models:
    def __init__(self):
        self._stable = None
        self._beta = None

    def _clients(self):
        if self._stable is None:
            from google import genai

            key = get_settings().require("GEMINI_API_KEY")
            self._stable = genai.Client(api_key=key)
            self._beta = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
        return self._stable, self._beta

    def _retry(self, label: str, fn):
        start = time.monotonic()
        for attempt in (1, 2):
            try:
                out = fn()
                log.info("model %s ok in %.1f s", label, time.monotonic() - start)
                return out
            except Exception as e:
                if attempt == 1 and _code(e) in RETRY_CODES:
                    log.warning("model %s %s, retrying", label, type(e).__name__)
                    time.sleep(RETRY_WAIT_S)
                    continue
                log.warning("model %s failed: %s", label, type(e).__name__)
                raise

    def call(self, role: str, prompt: str, schema: dict | None = None, thinking: str = "low"):
        """One model call. With a schema the reply is parsed JSON (structured output).
        Structured output (response_format + response_mime_type) is only accepted by the
        v1beta API (live error, 21 Nov), so schema calls use the v1beta client."""
        stable, beta = self._clients()
        client = stable if schema is None else beta
        model = get_settings().require(ROLE_MODEL[role])
        kwargs = dict(model=model, input=prompt, generation_config={"thinking_level": thinking},
                      timeout=CALL_TIMEOUT_S)
        if schema is not None:
            kwargs.update(response_format=schema, response_mime_type="application/json")
        interaction = self._retry(role, lambda: client.interactions.create(**kwargs))
        text = interaction.output_text or ""
        return json.loads(text) if schema is not None else text

    def decide(self, text: str, questions: dict) -> dict:
        """Decisions API: {qid: {"noul": p_yes, "confidence": c}}."""
        _, beta = self._clients()
        model = get_settings().require("MODEL_DECISIONS")
        d = self._retry("decisions", lambda: beta.decisions.create(
            model=model, input=[{"type": "text", "text": text}], questions=questions))
        return {qid: {"noul": a.noul, "confidence": a.confidence} for qid, a in (d.answers or {}).items()}

    def count_tokens(self, text: str) -> int:
        stable, _ = self._clients()
        model = get_settings().require("MODEL_ARGON")
        r = self._retry("count_tokens", lambda: stable.models.count_tokens(model=model, contents=text))
        return int(r.total_tokens)


_models: Models | None = None


def get_models():
    global _models
    if _models is None:
        _models = Models()
    return _models


def set_models(m) -> None:
    global _models
    _models = m
