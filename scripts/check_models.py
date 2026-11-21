"""Check every model answers. Bhargavi runs this in her own terminal.

    python scripts/check_models.py

Reads .env (python-dotenv). Prints one line per check:
    name | answered / failed / not configured | seconds | detail
Never prints the key, request headers, or error messages (they can echo
request details); only the exception class name and a short reply excerpt.
Exit code 0 only if every check answered.

Call shapes follow the hackathon builder guide (google-genai >= 3.2.0):
stable client + interactions.create for model calls; v1beta client for the
Decisions API and the Managed Agent.
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
# "low" is valid for all four models. Never pass temperature, top_p, top_k,
# a thinking budget, or "minimal".
SMOKE_THINKING_LEVEL = "low"
DECISION_TEXT = (
    "Page text: 'SG Unit-1 floor wash water transfer pumps, 2 nos.'\n"
    "Change: 'SG Unit-1 floor wash pumps: go to 2 working + 1 standby.'"
)
DECISION_INSTRUCTIONS = "Is the page about the same equipment as the change?"
AGENT_TASK = "Compute 2+2. Reply with the number only."
AGENT_TIMEOUT_S = 300
AGENT_MAX_TOTAL_TOKENS = 100_000
AGENT_POLL_S = 5


class NotConfigured(Exception):
    """A required setting is empty."""


def setting(name: str) -> str:
    value = get_settings().get(name)
    if not value:
        raise NotConfigured(name)
    return value


def make_clients():
    """Stable client for model calls; v1beta client for Decisions and Managed Agents."""
    from google import genai

    key = get_settings().require("GEMINI_API_KEY")
    stable = genai.Client(api_key=key)
    beta = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
    return stable, beta


def check_chat(stable, env_name: str) -> str:
    interaction = stable.interactions.create(
        model=setting(env_name),
        input=PROMPT,
        generation_config={"thinking_level": SMOKE_THINKING_LEVEL},
    )
    text = (interaction.output_text or "").strip()
    if not text:
        raise RuntimeError("empty reply")
    return text


def check_decisions(beta) -> str:
    decision = beta.decisions.create(
        model=setting("MODEL_DECISIONS"),
        input=[{"type": "text", "text": DECISION_TEXT}],
        questions={"q1": {"type": "noul", "instructions": DECISION_INSTRUCTIONS}},
    )
    answer = decision.answers["q1"]
    return f"P(yes)={answer.noul:.2f} conf={answer.confidence:.2f}"


def check_agent(beta) -> str:
    deadline = time.monotonic() + AGENT_TIMEOUT_S
    interaction = beta.interactions.create(
        agent=setting("MANAGED_AGENT"),
        environment="remote",
        agent_config={
            "type": "antigravity",
            "model": setting("MODEL_NEON"),
            "max_total_tokens": AGENT_MAX_TOTAL_TOKENS,
        },
        input=AGENT_TASK,
        timeout=AGENT_TIMEOUT_S,
    )
    while str(interaction.status).lower().endswith("in_progress"):
        if time.monotonic() > deadline:
            raise TimeoutError("agent did not finish in 300 s")
        time.sleep(AGENT_POLL_S)
        interaction = beta.interactions.get(interaction.id, timeout=AGENT_TIMEOUT_S)
    text = (interaction.output_text or "").strip()
    if not text:
        raise RuntimeError(f"no output, status {interaction.status}")
    sandbox = "sandbox id returned" if interaction.environment_id else "no sandbox id"
    return f"{text[:20]} ({sandbox})"


def run(name: str, fn) -> bool:
    start = time.monotonic()
    try:
        detail, status, ok = fn()[:40], "answered", True
    except NotConfigured as e:
        status, detail, ok = "not configured", str(e), False
    except Exception as e:  # report the class name only, never the message
        status, detail, ok = "failed", type(e).__name__, False
    seconds = time.monotonic() - start
    print(f"{name:<14}| {status:<15}| {seconds:6.1f} s | {detail}", flush=True)
    return ok


def main() -> int:
    try:
        stable, beta = make_clients()
    except MissingSetting as e:
        print(f"cannot start: {e}")
        return 1

    results = [run(name, lambda env=env: check_chat(stable, env)) for name, env in CHAT_MODELS]
    results.append(run("Decisions API", lambda: check_decisions(beta)))
    results.append(run("Managed Agent", lambda: check_agent(beta)))

    print(f"\n{sum(results)} of {len(results)} answered")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
