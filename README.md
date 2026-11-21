# Interlock

**No plant change is signed off until every document agrees, and the numbers still work.**

Type a change to a process plant. Interlock finds every page about that equipment (under all its names), boxes it on the real P&ID drawing, runs the engineering calculations in code, and gives a verdict with the evidence. A Gemini Managed Agent then proposes a fix, which the server re-checks and marks proven or refused, and the plant remembers every approved change.

Built at the Gemini 4 NYC Hackathon, 21 Nov 2026.

- What and why: [`docs/PROJECT.md`](docs/PROJECT.md)
- How it works: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- The engineering rules: [`docs/RULES.md`](docs/RULES.md)
- Results and where it fails: [`docs/EVAL.md`](docs/EVAL.md)
- Build plan: [`docs/PHASES.md`](docs/PHASES.md)

## Built today

All code and documents in this repo were written during the event on 21 Nov 2026. The public documents used for testing are listed in [`docs/EVAL.md`](docs/EVAL.md).

## Live

URL: https://interlock-67888742605.us-central1.run.app

Video: added in phase 6 (recorded from the live URL at tag `phase-6-ship`).

## Run it

Windows PowerShell, from the repo root. Python 3.13 (python.org).

```powershell
conda deactivate                      # only if a conda env is active
py -3.13 -m venv .venv                # once
.venv\Scripts\activate
pip install -r requirements.txt
pytest -q                             # tests
uvicorn app.api.main:app --reload --env-file .env   # local, http://127.0.0.1:8000
```

Copy `.env.example` to `.env` and fill it in yourself; it is git-ignored. Check every model answers: `python scripts/check_models.py`.

Deploy: [`deploy/COMMANDS.md`](deploy/COMMANDS.md).

## Libraries

Pinned in `requirements.txt`.

| Library | Used for |
|---|---|
| fastapi | HTTP API |
| uvicorn[standard] | Server |
| google-genai | Gemini models |
| google-cloud-firestore | Plants, changes, register, jobs |
| google-cloud-storage | Uploaded PDFs, page text and images |
| pyyaml | `rules.yaml` |
| pymupdf | PDF text, page images, text positions |
| python-dotenv | Loads `.env` for local scripts |
| pytest, httpx | Tests |
