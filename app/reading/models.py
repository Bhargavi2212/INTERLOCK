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
    "drawing": "MODEL_ARGON",
    "one_call": "MODEL_ARGON",
    "agent_answer": "MODEL_HYDROGEN",
}
RETRY_CODES = {429, 500, 502, 503, 504}
EXTRACT_PROMPT = "Turn this agent report into the JSON schema. Copy, never invent.\n\n"
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

    def call(self, role: str, prompt: str, schema: dict | None = None, thinking: str = "low",
             usage: dict | None = None):
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
        u = getattr(interaction, "usage", None)
        if u is not None:
            counts = {"input": u.total_input_tokens, "cached": u.total_cached_tokens,
                      "output": u.total_output_tokens, "thought": u.total_thought_tokens}
            log.info("model %s tokens %s", role, counts)
            if usage is not None:
                usage.update(counts)
        text = interaction.output_text or ""
        return json.loads(text) if schema is not None else text

    def see(self, role: str, prompt: str, png: bytes, schema: dict, thinking: str = "low",
            usage: dict | None = None):
        """Text + one PNG (inline base64; the bucket stays private) -> parsed JSON.
        Input part shape from the installed SDK's ImageContent: {"type": "image", "data", "mime_type"}."""
        import base64

        _, beta = self._clients()
        model = get_settings().require(ROLE_MODEL[role])
        parts = [{"type": "text", "text": prompt},
                 {"type": "image", "data": base64.b64encode(png).decode("ascii"), "mime_type": "image/png"}]
        interaction = self._retry(role, lambda: beta.interactions.create(
            model=model, input=parts, generation_config={"thinking_level": thinking}, timeout=CALL_TIMEOUT_S,
            response_format=schema, response_mime_type="application/json"))
        u = getattr(interaction, "usage", None)
        if u is not None and usage is not None:
            usage.update({"input": u.total_input_tokens, "cached": u.total_cached_tokens,
                          "output": u.total_output_tokens})
        return json.loads(interaction.output_text or "{}")

    def agent(self, prompt: str, environment, previous_id: str | None, schema: dict, cfg: dict) -> dict:
        """Managed Agent run (v1beta). environment: {"type": "remote", "sources": [...]} for a new
        sandbox, or an environment_id string to reuse one. Structured answer via response_format;
        if the agent call refuses it, one Hydrogen structured call reads the final text instead.
        Polls to cfg timeout_s. -> {answer, environment_id, interaction_id}."""
        _, beta = self._clients()
        settings = get_settings()
        kwargs = dict(agent=settings.require("MANAGED_AGENT"), environment=environment, input=prompt,
                      agent_config={"type": "antigravity", "model": settings.require(cfg["model_env"]),
                                    "max_total_tokens": cfg["max_total_tokens"]},
                      timeout=cfg["timeout_s"])
        if previous_id:
            kwargs["previous_interaction_id"] = previous_id
        structured = True
        try:
            inter = self._retry("agent", lambda: beta.interactions.create(
                **kwargs, response_format=schema, response_mime_type="application/json"))
        except Exception as e:
            if _code(e) != 400:
                raise
            structured = False
            inter = self._retry("agent", lambda: beta.interactions.create(**kwargs))
        deadline = time.monotonic() + cfg["timeout_s"]
        while str(inter.status).lower().endswith("in_progress"):
            if time.monotonic() > deadline:
                raise TimeoutError("agent did not finish in time")
            time.sleep(cfg["poll_s"])
            inter = beta.interactions.get(inter.id, timeout=cfg["timeout_s"])
        text = (inter.output_text or "").strip()
        if text.startswith("```"):   # the agent fenced its JSON despite response_format (live, 21 Nov)
            text = text.strip("`").split("\n", 1)[-1] if text.lower().startswith("```json") else text.strip("`")
            text = text.rsplit("```", 1)[0].strip()
        if structured:
            try:
                answer = json.loads(text)
            except ValueError:  # the agent answered in prose despite response_format
                answer = None   # run.py copies its raw text into the schema, then validates
        else:
            answer = self.call("agent_answer", EXTRACT_PROMPT + text, schema, "low")
        return {"answer": answer, "raw": text[:6000], "environment_id": getattr(inter, "environment_id", None),
                "interaction_id": inter.id}

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
