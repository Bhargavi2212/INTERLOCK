"""Check every model answers. Bhargavi runs this in her own terminal.

    python scripts/check_models.py

Reads .env (python-dotenv). Prints one line per check:
    name | answered / failed / not configured | seconds | error type
Never prints the key, request headers, or error messages (they can echo
request details); only the exception class name and at most 20 characters
of a reply. Exit code 0 only if every check answered.
"""

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.config import MissingSetting, get_settings  # noqa: E402

PROMPT = "Reply with the single word OK."
CHAT_MODELS = [
    ("Hydrogen", "MODEL_HYDROGEN"),
    ("Argon", "MODEL_ARGON"),
    ("Carbon", "MODEL_CARBON"),
    ("Neon", "MODEL_NEON"),
]
AGENT_TIMEOUT_S = 300


class NotConfigured(Exception):
    """The setting or the call shape is not available yet."""


def make_client():
    from google import genai
    from google.genai import types

    key = get_settings().require("GEMINI_API_KEY")
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=120_000))


def check_chat(client, env_name: str) -> str:
    model = get_settings().get(env_name)
    if not model:
        raise NotConfigured(env_name)
    response = client.models.generate_content(model=model, contents=PROMPT)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("empty reply")
    return text


def check_decisions(client) -> str:
    if not get_settings().get("MODEL_DECISIONS"):
        raise NotConfigured("MODEL_DECISIONS")
    # Call shape comes from the builder resources (plan N1); wired when received.
    raise NotConfigured("Decisions API call shape")


def check_agent(client) -> str:
    if not get_settings().get("MANAGED_AGENT"):
        raise NotConfigured("MANAGED_AGENT")
    # Call shape comes from the builder resources (plan N2); wired when received.
    raise NotConfigured("Managed Agent call shape")


def run(name: str, fn) -> bool:
    start = time.monotonic()
    try:
        reply = fn()
        status, detail, ok = "answered", f'"{reply[:20]}"', True
    except NotConfigured as e:
        status, detail, ok = "not configured", str(e), False
    except Exception as e:  # report the class name only, never the message
        status, detail, ok = "failed", type(e).__name__, False
    seconds = time.monotonic() - start
    print(f"{name:<14}| {status:<15}| {seconds:6.1f} s | {detail}", flush=True)
    return ok


def main() -> int:
    try:
        client = make_client()
    except MissingSetting as e:
        print(f"cannot start: {e}")
        return 1

    results = [run(name, lambda env=env: check_chat(client, env)) for name, env in CHAT_MODELS]
    results.append(run("Decisions API", lambda: check_decisions(client)))
    results.append(run("Managed Agent", lambda: check_agent(client)))

    passed = sum(results)
    print(f"\n{passed} of {len(results)} answered")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
