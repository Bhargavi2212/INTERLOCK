# Phase 0 spec — Setup and production skeleton

Owner docs: `PHASES.md` (phase 0), `ARCHITECTURE.md` §2, §7, §8. Time: 11:30-12:10.

## Goal

An empty but real product running on Cloud Run, reachable from a phone, with every model reachable from a script. Nothing product-specific yet.

## Claude Code builds

0. **Git:** `git init -b main`; first commit = the existing docs only (proves docs came before code). Bhargavi creates an empty **public** GitHub repo in the browser (`gh` is not installed) and gives the URL; it is added as `origin`.
1. **The whole repo layout** exactly as the tree in `ARCHITECTURE.md` §2: every folder, every Python package with an empty `__init__.py`, `.gitkeep` in empty non-package folders (`eval/keys`, `eval/baselines`, `eval/results`; `docs/specs` already exists).
1a. **The virtual environment:** check `python --version`; create `.venv` with the python.org interpreter (`py -3.13 -m venv .venv`), not the Anaconda one; install `requirements.txt` into it; all later commands run inside `.venv`. `.venv/` stays git-ignored.
2. **Python project:** Python 3.13 locally and in the Dockerfile (same major.minor); `requirements.txt` with pinned versions of `fastapi`, `uvicorn[standard]`, `google-genai`, `google-cloud-firestore`, `google-cloud-storage`, `pyyaml`, `pytest`, `httpx`, `python-dotenv`. Nothing else in this phase. (No `google-cloud-secret-manager`: Cloud Run's `--set-secrets` injects secrets as environment variables.)
2a. **`pytest.ini`:** `pythonpath = .` and `testpaths = tests`, so `pytest` from the repo root imports `app`.
3. **`app/config.py`:** reads settings from environment variables named in `.env.example`. Never logs or returns `GEMINI_API_KEY` (hidden from repr and serialisation). **Required settings are checked when first used, not at import**, so tests and the container start without a `.env`. A missing setting raises a clear error naming the variable, not its value. `APP_VERSION` defaults to `"dev"`.
4. **`app/api/main.py`:** FastAPI app.
   - `GET /health` → `{"status": "ok", "version": APP_VERSION}`. The version comes from the `APP_VERSION` environment variable, set to the git short sha at deploy (the container has no `.git`).
   - `GET /` → serves `web/index.html` (a placeholder page saying "Interlock" and the version).
5. **`tests/test_health.py`:** `/health` returns 200 and `status: ok`; `/` returns 200 and contains "Interlock"; the app imports with no environment variables set.
6. **`scripts/check_models.py`:** loads `.env` (python-dotenv). Call shapes per `ARCHITECTURE.md` §3 (builder guide). For each of `MODEL_HYDROGEN`, `MODEL_ARGON`, `MODEL_CARBON`, `MODEL_NEON`, sends "Reply with the single word OK." via `interactions.create` with `thinking_level` `low` and prints `model name | answered / failed | seconds | error type if failed` (exception class name only, never its message). Then one Decisions API `noul` question (v1beta client). Then one **Managed Agent smoke check** (`MANAGED_AGENT`, model `MODEL_NEON`, `max_total_tokens` set, timeout 300 s): a trivial task, printed answered / failed. Never prints the key or request headers. Exit code 0 only if all six answered.
7. **`Dockerfile`** at the repo root: `python:3.13-slim`, installs requirements, copies `app/` and `web/`, runs `uvicorn app.api.main:app --host 0.0.0.0 --port $PORT`.
8. **`.dockerignore`:** `.env*` (except `.env.example`), `.git`, `data/`, `eval/results/`, `*.pdf`, `__pycache__`, `.venv`, `docs/DECISIONS.md`.
8a. **`.gcloudignore`:** same exclusions, so `gcloud run deploy --source .` never uploads `.env`, `.venv`, `data/` or PDFs (the upload happens before `.dockerignore` applies).
9. **`deploy/COMMANDS.md`:** the exact PowerShell-ready gcloud commands below, with `<PROJECT_ID>` placeholders, for Bhargavi to run. Secret values are typed at a prompt or piped from a file she controls, never written into the command.
10. **README "Run it"** section: activate `.venv`, install, run tests, run locally. **README "Libraries"**: the pinned list.
11. **`CLAUDE.md` "Commands"** filled in: tests, local run, deploy.

## Bhargavi runs herself (Claude Code never sees the key)

1. Activate the venv in her terminal: `conda deactivate`, then `.venv\Scripts\activate`.
2. Fill `.env` from the builder resources (key + model strings + Decisions API and Managed Agent ids).
3. Run `python scripts/check_models.py`; share only the printed table.
4. GCP, in her own project (from `deploy/COMMANDS.md`):
   - Enable APIs: Cloud Run, Cloud Build, Artifact Registry, Secret Manager, Firestore, Cloud Storage, IAM Credentials.
   - Firestore database in Native mode.
   - Bucket `<PROJECT_ID>-interlock`, uniform access, with a CORS rule allowing `PUT` from the Cloud Run URL (added after the first deploy; `ARCHITECTURE.md` §1a).
   - Service account `interlock-run` with: Secret Manager Secret Accessor, Cloud Datastore User, Storage Object Admin on the bucket, and Service Account Token Creator on itself.
   - Secrets `GEMINI_API_KEY` and `ACCESS_CODE`.
   - Deploy: `gcloud run deploy interlock --source . --region us-central1 --service-account interlock-run@<PROJECT_ID>.iam.gserviceaccount.com --set-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest,ACCESS_CODE=ACCESS_CODE:latest --set-env-vars APP_VERSION=<git short sha>,<MODEL_*, MANAGED_AGENT and GCP settings> --timeout 900 --memory 2Gi --cpu 2 --min-instances 1 --max-instances 1 --no-cpu-throttling --allow-unauthenticated`

## In parallel: the unseen changes (set E)

Ask 3-5 people for one change each to the BHEL plant. With each author, write `eval/keys/E1.json` … in the format in `EVAL.md` §2 (pages as `{file, page}`, `"unit": "count"` for counts, `documents_disagree`, `expected_verdict`), and commit **before any system runs on them**.

## Out of scope in phase 0

Upload, ingest, any model call from the app, rules, the agent, the real screen, the access code check.

## Done when

- [ ] Repo layout matches the `ARCHITECTURE.md` §2 tree (folder by folder).
- [ ] `.venv` exists, requirements installed in it, and `git status` does not list it.
- [ ] `pytest` passes inside `.venv`.
- [ ] The live Cloud Run URL shows the placeholder page and `/health` returns ok with the deployed git sha as version.
- [ ] `check_models.py` gets "answered" from Hydrogen, Argon, Carbon, Neon, the Decisions API and the Managed Agent.
- [ ] At least 3 `eval/keys/E*.json` committed.
- [ ] `git grep` for the key's first characters returns nothing; `git status` does not list `.env` or `docs/DECISIONS.md`.
- [ ] `PHASES.md` phase 0 Status set to `done (phase-0-setup)`; tag pushed.
