# CLAUDE.md

Instructions for Claude Code in this repo. This file points to the docs; it does not repeat them.

## Read first, every task

- `docs/PROJECT.md` — what we build and what we do not
- `docs/ARCHITECTURE.md` — components, model jobs, data, deployment
- `docs/PHASES.md` — the current phase and its done-when check
- `docs/RULES.md` — owns every formula and limit
- `docs/EVAL.md` — how results are measured
- `docs/specs/PHASE_N.md` — the detailed spec for the phase in progress

## How to work

1. Build only what the phase marked `Status: in progress` in `docs/PHASES.md` lists. Stop at its done-when check and report the result, pass or fail, with evidence.
2. If a task conflicts with a doc, stop and say so. Do not silently pick one.
3. Any change to behaviour updates the doc that owns it **in the same commit**. Any choice between options is explained in the commit message.
4. Small commits, message says what changed. Tag at phase end: `phase-N-name`.
5. Before every commit: `pytest` passes.

## Hard rules

- **No model calls in `app/rules/`.** Rules are data in `app/rules/rules.yaml` and must match `docs/RULES.md`. Never hard-code a limit in Python.
- **Every value read from a document carries `file`, `page`, `unit` and either a `quote` (text) or a `box` on a drawing whose text-layer label the code has verified,** and the evidence check confirms it before the value reaches the rules.
- **Unknown or missing input → held.** Never guess a value or a unit.
- **The agent never decides.** The server re-runs the rules and the register check on every agent fix.
- **Measured numbers** live only in `docs/EVAL.md`; limits only in `docs/RULES.md`. Other files point to them, never copy them. One exception: `README.md` may hold one summary table copied from `EVAL.md` §5, labelled as a copy; `EVAL.md` stays the source.
- **Secrets:** never read, open, print, log or commit `.env` or any key, and never run commands that would show them. Bhargavi creates secrets and runs anything that needs the key herself; give her the command instead. Keys come from environment variables locally and Secret Manager in production. Model strings come from `MODEL_*` environment variables.
- **New work only:** no code copied from outside this repo or from before 21 Nov 2026. Third-party libraries are fine; list them in `README.md`.
- **No dashboards.** One screen: change in, evidence, drawing, calc sheet, verdict, fix.

## Words

- Rule result: **OK / flagged / held**
- Verdict: see `docs/RULES.md` (never "PASS")
- **The register**: approved changes for a plant
- **The plant**: one uploaded document set

## Commands

Inside `.venv` (`.venv\Scripts\activate`):

```
# tests
pytest -q

# run locally (development only)
uvicorn app.api.main:app --reload --env-file .env

# deploy (Bhargavi runs it)
see deploy/COMMANDS.md, block 6
```
