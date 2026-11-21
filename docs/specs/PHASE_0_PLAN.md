# Phase 0 — build plan (for approval)

Implements `docs/specs/PHASE_0.md`. **Approved 21 Nov 2026** with four changes, applied below: secrets written to a temp file with `[IO.File]::WriteAllText` (never piped); Managed Agent timeout 300 s; `google-genai` pinned to the builder resources' version if they name one; `.gitattributes` yes.

---

## 0. What I need from Bhargavi first

| # | Item | Why | Blocks |
|---|---|---|---|
| N1 | ✅ Received; recorded in `ARCHITECTURE.md` §3. Decisions API call shape. | `check_models.py` must ask it one question in the documented shape | Step 5 |
| N2 | ✅ Received; recorded in `ARCHITECTURE.md` §3. Managed Agent call shape. | `check_models.py` smoke check | Step 5 |
| N3 | ✅ `https://github.com/Bhargavi2212/INTERLOCK.git` | `origin` remote, pushed tag | Step 1 |
| N4 | GCP **project id** (only the id; I put `<PROJECT_ID>` in the commands file either way) | Ready-to-paste commands | Step 7 (optional) |
| N5 | ✅ `data/bhel/Part1.pdf`-`Part5.pdf`, 150/150/150/150/251 = 851 pages; in `EVAL.md` §2 | Set E keys use `{file, page}` | — |

If N1 or N2 is not available, those two checks print `not configured` and the done-when check for them fails until they arrive. Everything else proceeds.

## 1. Machine facts (checked)

| Tool | Found | Use |
|---|---|---|
| `python` on PATH | Anaconda 3.12.7 | **Not used** for the venv |
| `py` launcher | python.org 3.13 (default); its "3.12" is the Anaconda install | `py -3.13 -m venv .venv` |
| git | 2.50, `core.autocrlf` converts to CRLF | see 2.3 |
| gcloud | 562.0.0 | Bhargavi deploys |
| docker | 29.4.3 | local container check (step 6) |
| gh | not installed | repo created in browser |

**Changed during step 3:** Python 3.13 (python.org), not 3.12. `py -3.12` turned out to be the Anaconda interpreter, which the plan rules out; 3.13 is the only python.org one here. The Dockerfile uses `python:3.13-slim` to match. All 9 pins install on 3.13.

---

## 2. Steps

Each step ends with `pytest -q` (from step 3 on) and a small commit. Commit messages end with the attribution line. I never open, read or print `.env`.

### Step 1 — Git (spec item 0) · ~3 min

1. `git init -b main`.
2. Check `git status --ignored` shows `.env` (if present) and `docs/DECISIONS.md` as ignored before anything is added.
3. Commit 1: `docs: initial project docs` — README, CLAUDE.md, `.gitignore`, `.env.example`, `docs/` (without DECISIONS.md). This commit proves the docs came before code.
4. `git remote add origin <N3>`. Push is done by Bhargavi (her credentials), or by me if `git push` works without a prompt.

### Step 2 — Repo layout (spec items 1, 2a, 8a) · ~3 min

Create exactly the `ARCHITECTURE.md` §2 tree:

```
app/__init__.py, app/config.py
app/{api,ingest,reading,drawing,rules,register,explain,verdict,agent,jobs,store}/__init__.py
web/index.html
tests/test_health.py, tests/rules/.gitkeep   (no tests/__init__.py: pytest.ini handles imports)
eval/keys/.gitkeep, eval/baselines/.gitkeep, eval/results/.gitkeep
scripts/check_models.py
deploy/COMMANDS.md
Dockerfile, .dockerignore, .gcloudignore, pytest.ini, requirements.txt
```

`data/` is not created in git (ignored); a local `data/` is fine.

**2.3 Line endings (approved):** `.gitattributes` with `* text=auto eol=lf`, plus `*.ps1 eol=crlf`, and `*.pdf *.png binary`. Reason: git here converts to CRLF, and the Dockerfile and any shell lines run in Linux.

Commit 2: `phase 0: repo layout, pytest config, ignore files`.

### Step 3 — Virtual environment and requirements (spec items 1a, 2) · ~5 min

1. `py -3.13 --version` → 3.13.2 (python.org).
2. `py -3.13 -m venv .venv`.
3. `.venv/Scripts/python -m pip install --upgrade pip`.
4. Install the 9 packages unpinned: `fastapi`, `uvicorn[standard]`, `google-genai`, `google-cloud-firestore`, `google-cloud-storage`, `pyyaml`, `pytest`, `httpx`, `python-dotenv`.
5. Write `requirements.txt` with **only those 9**, each pinned `==` to the version pip installed (read via `pip show`), not a full `pip freeze`. **Exception:** `google-genai` is pinned to the version the builder resources specify, if they name one.
6. Reinstall from `requirements.txt` into the venv to prove the pins resolve.
7. `git status` must not list `.venv`.

Included in commit 3.

### Step 4 — Config, API, page, tests (spec items 3, 4, 5) · ~10 min

**`app/config.py`**
- `Settings` built from `os.environ` on first call of `get_settings()` (cached).
- Fields: every name in `.env.example` (`GEMINI_API_KEY`, `MODEL_HYDROGEN`, `MODEL_ARGON`, `MODEL_CARBON`, `MODEL_NEON`, `MODEL_DECISIONS`, `MANAGED_AGENT`, `GCP_PROJECT`, `GCP_REGION`, `GCS_BUCKET`, `FIRESTORE_DATABASE`, `ACCESS_CODE`, `APP_VERSION`).
- `require(name)` → returns the value, or raises `MissingSetting("GEMINI_API_KEY is not set")` — names only, never values.
- The key and access code are held so they never appear in `repr()`, `str()`, `dict()` or JSON of the settings object (custom `__repr__` that lists names only, with `***` for secrets that are set).
- No validation at import. `APP_VERSION` defaults to `"dev"`; `GCP_REGION` to `us-central1`.
- Does **not** load `.env` itself (the app gets environment variables from uvicorn `--env-file` locally and from Cloud Run in production).

**`app/api/main.py`**
- `app = FastAPI(title="Interlock")`.
- `GET /health` → `{"status": "ok", "version": settings.app_version}`.
- `GET /` → `FileResponse("web/index.html")` (path resolved from the repo root, not the working directory).
- Nothing else. No model client is created.

**`web/index.html`**
- One self-contained page: "Interlock", the one-line tagline from `README.md`, and the version filled in from `/health` with a few lines of inline JS. Readable on a phone (viewport meta, no external assets). Placeholder only.

**`tests/test_health.py`** (FastAPI `TestClient`, uses `httpx`)
- `/health` → 200, `status == "ok"`, `version` is a string.
- `/` → 200, body contains "Interlock".
- With every `.env.example` variable removed from the environment (monkeypatch), the app still imports and `/health` answers.
- `settings` repr with a fake `GEMINI_API_KEY="test-not-a-key"` does not contain that string.

**`tests/rules/`**: `.gitkeep` only (phase 1 fills it).

Run `pytest -q` → must pass. Commit 3: `phase 0: config, /health, placeholder page, tests, pinned requirements`.

### Step 5 — `scripts/check_models.py` (spec item 6) · ~8 min

- Loads `.env` with `python-dotenv` (only Bhargavi runs it; I never run it).
- Uses `google-genai` `Client(api_key=...)` and `client.models.generate_content(model=<MODEL_*>, contents="Reply with the single word OK.")`.
- Six checks, run in order, each timed:

| Check | Variable | Call | answered when |
|---|---|---|---|
| Hydrogen | `MODEL_HYDROGEN` | generate_content | any non-empty text |
| Argon | `MODEL_ARGON` | generate_content | any non-empty text |
| Carbon | `MODEL_CARBON` | generate_content | any non-empty text |
| Neon | `MODEL_NEON` | generate_content | any non-empty text |
| Decisions API | `MODEL_DECISIONS` | per N1, one yes/no test question ("Is a 'floor wash pump' the same item as a 'floor wash water transfer pump'?") | a probability or decision comes back |
| Managed Agent | `MANAGED_AGENT` | per N2, trivial task ("Return the number 2+2.") with a **300 s** timeout | the task completes with output |

- Output, one line per check: `Hydrogen | answered | 1.8 s |` or `Carbon | failed | 0.4 s | PermissionDenied`. Error = exception **class name only**; messages are not printed because they can echo request details.
- A variable that is empty prints `not configured`.
- Never prints the key, headers, or full responses (first 20 characters of the reply at most, to show it answered).
- Exit code 0 only if all six answered.
- Not imported by the app; not run by pytest (no network in tests).

Commit 4: `phase 0: check_models script`.

### Step 6 — Container (spec items 7, 8, 8a) · ~6 min

**`Dockerfile`**
```
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY web/ web/
CMD exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
```
(`pytest`/`httpx` get installed in the image too; acceptable today, noted.)

**`.dockerignore` and `.gcloudignore`** (same list): `.env`, `.env.*`, `!.env.example`, `.git`, `.venv`, `data/`, `eval/results/`, `*.pdf`, `__pycache__/`, `.pytest_cache/`, `docs/DECISIONS.md`, `*.key`, `*credentials*.json`, `service-account*.json`. `.gcloudignore` also ignores `.gitignore` and itself is fine to upload.

**Local check (no key needed):**
1. `docker build -t interlock:dev .`
2. `docker run -d -p 8080:8080 -e APP_VERSION=local interlock:dev`
3. `curl localhost:8080/health` → `{"status":"ok","version":"local"}`; `curl localhost:8080/` contains "Interlock".
4. `docker exec` → `ls /srv` shows only `app web requirements.txt` (proves no `.env`, PDFs or venv inside).
5. Stop and remove the container.

### Step 7 — `deploy/COMMANDS.md` (spec item 9) · ~6 min

PowerShell, in order, each block with one line saying what it does and how to check it worked:

1. `gcloud config set project <PROJECT_ID>`
2. Enable APIs: `run`, `cloudbuild`, `artifactregistry`, `secretmanager`, `firestore`, `storage`, `iamcredentials`.
3. `gcloud firestore databases create --location=us-central1` (Native mode default).
4. `gcloud storage buckets create gs://<PROJECT_ID>-interlock --location=us-central1 --uniform-bucket-level-access`
5. Service account `interlock-run` + roles: `secretmanager.secretAccessor`, `datastore.user` (project); `storage.objectAdmin` (bucket); `iam.serviceAccountTokenCreator` on itself. Plus the Cloud Build / compute default service account permissions `--source` deploys need, if the project is new.
6. Secrets, value typed at a hidden prompt, **never piped and never in the command**: read with `Read-Host -AsSecureString`, convert to plain text in memory, write it with `[IO.File]::WriteAllText($path, $plain)` (no trailing newline) to a temp file, run `gcloud secrets create GEMINI_API_KEY --data-file=$path`, then delete the file and clear the variables. Same for `ACCESS_CODE`.
7. Deploy:
   ```
   $sha = git rev-parse --short HEAD
   gcloud run deploy interlock --source . --region us-central1 `
     --service-account interlock-run@<PROJECT_ID>.iam.gserviceaccount.com `
     --set-secrets GEMINI_API_KEY=GEMINI_API_KEY:latest,ACCESS_CODE=ACCESS_CODE:latest `
     --set-env-vars "APP_VERSION=$sha,MODEL_HYDROGEN=...,MODEL_ARGON=...,MODEL_CARBON=...,MODEL_NEON=...,MODEL_DECISIONS=...,MANAGED_AGENT=...,GCP_PROJECT=<PROJECT_ID>,GCP_REGION=us-central1,GCS_BUCKET=<PROJECT_ID>-interlock,FIRESTORE_DATABASE=(default)" `
     --timeout 900 --memory 2Gi --cpu 2 --min-instances 1 --max-instances 1 --no-cpu-throttling --allow-unauthenticated
   ```
   Model strings are not secrets; she pastes them from `.env` herself.
8. `$url = gcloud run services describe interlock --region us-central1 --format "value(status.url)"`
9. CORS: write `cors.json` (method `PUT`, origin `$url`, header `Content-Type`), `gcloud storage buckets update gs://<PROJECT_ID>-interlock --cors-file=cors.json`.
10. Check: `curl $url/health` → version equals `$sha`.

Note in the file: re-deploys after phases 2, 3, 4, 6 repeat only block 7 and 10.

### Step 8 — Docs (spec items 10, 11) · ~4 min

- `README.md` **Run it**: `conda deactivate`; `.venv\Scripts\activate`; `pip install -r requirements.txt`; `pytest -q`; `uvicorn app.api.main:app --reload --env-file .env`; deploy → `deploy/COMMANDS.md`.
- `README.md` **Libraries**: the 9 pinned packages, one line each with what it is for.
- `CLAUDE.md` **Commands**: tests, local run, deploy (pointer to `deploy/COMMANDS.md`).
- `ARCHITECTURE.md` §2 tree: add `.gitattributes`.

Commit 5: `phase 0: Dockerfile, ignore files, deploy commands, README and CLAUDE commands`.

### Step 9 — Bhargavi's part (in parallel with steps 2-8)

1. `conda deactivate`; `.venv\Scripts\activate` (after step 3).
2. Fill `.env`.
3. `python scripts/check_models.py` → paste only the table.
4. Run `deploy/COMMANDS.md` → paste the service URL.
5. Set E: 3-5 changes from other people, keys in `EVAL.md` §2 format, committed before any run. I do not write or edit these files.

### Step 10 — Done-when check and close · ~5 min

| Check | How I verify | Evidence reported |
|---|---|---|
| Layout matches §2 tree | list folders, compare to tree line by line | the listing |
| `.venv` exists, not tracked | `ls .venv`, `git status --porcelain` | output |
| `pytest` passes in `.venv` | `.venv/Scripts/python -m pytest -q` | output |
| Live URL works | `curl <URL>/health` and `<URL>/` | JSON + version = deployed sha |
| All six models answer | Bhargavi's pasted table | the table |
| ≥3 set E keys | `git log --format="%h %ad" -- eval/keys/E*.json` | commit list with times |
| No key in git | `git grep -n "AIza"` (public Google key prefix, no secret needed) returns nothing; `git status --ignored` shows `.env`, `docs/DECISIONS.md` ignored | output |
| Close | Status → `done (phase-0-setup)`; commit; `git tag phase-0-setup`; push with tags | tag name |

Any failed check is reported as failed with its output; the phase is not marked done.

---

## 3. Out of scope (not touched in phase 0)

Upload, ingest, any model call from the app, rules, verdict, register, agent, the real screen, the access-code check, Firestore/Storage client code (packages installed only), set A/B/F keys (phase 1).

## 4. Risks and what I do

| Risk | Response |
|---|---|
| N1/N2 snippets not available | Those checks print `not configured`; rest of phase 0 completes; flagged in the report |
| A pinned package fails to install on 3.12 | Pick the newest version that installs, note it in the commit message |
| `gcloud run deploy --source` fails on permissions in a new project | Add the missing role command to `COMMANDS.md`; cut-line 12:05 says fix Cloud Run before anything else |
| Push needs credentials I don't have | Bhargavi runs `git push -u origin main --tags` |

## 5. Approve

Approved. Building from step 1.
