# Architecture

What the system is made of and how a change flows through it. What we build and why: `PROJECT.md`. Formulas, limits and units: `RULES.md`. Measured numbers: `EVAL.md`.

---

## 1. The flow of one change

```
 engineer uploads the plant's documents              engineer types a change
 (a whole folder, or several files)                            |
            |                                                  v
            v                                     [1 Understand the change]  Neon
 [0 Ingest] background job: text + page images                 |
            |                                                  |
            +---------------------------+----------------------+
                                        v
 [2 Find the item]   Argon long read over the plant's pages (automatic cache, see §7)
                     + code search over every page (all names, spacing ignored)
                                        |
 [3 Same item?]      Decisions API on each candidate page (probability)
                                        |
 [4 Pull the values] Argon, structured output: value, unit, page, exact quote; also
                     design-basis limits stated in the documents (e.g. a velocity table)
                                        |
 [5 Evidence check]  code: quote is on that page, value is in the quote, unit is known
                                        |
          +-----------------------------+-----------------------------+
          v                             v                             v
 [6 Drawing] Argon boxes the   [7 Rules] code only:          [7b Register] code: does the change
   item on the P&ID image        OK / flagged / held           clash with an approved change?
          |                             |                             |
          |                    [8 Explain] Carbon: which page is likely right,
          |                        what goes wrong in the plant
          +-----------------------------+-----------------------------+
                                        v
          [9 Verdict] code: BLOCK / REVIEW / no conflicts found in N pages checked
                      Hydrogen: one-line headline per finding
                                        |
                          engineer asks for a fix
                                        v
 [10 Managed Agent] (Neon) in the plant's persistent sandbox: searches for a fix,
     runs the rules on each candidate, up to 8 tries, proposes one or refuses with reasons
                                        |
 [11 Server re-check] the server re-runs the rules AND the register check on the proposed fix.
     "Proven" is shown only if the server agrees. The agent never decides.
                                        |
 [12 Approve] engineer approves -> register updated in Firestore
```

Steps 1-9 run as a **background job**: `POST /plants/{id}/changes` returns a job id at once, and the screen shows progress (finding pages, same-item check, values, drawing, rules, verdict). Target: under 90 s per change on BHEL.

## 1a. Uploading a plant

The engineer creates a plant and adds its documents in one of two ways:

- **A whole folder** (with sub-folders), picked or dragged into the page.
- **Several individual files**, picked or dragged. More files can be added later; each batch is ingested into the same plant.

What happens:

1. The browser lists the files, keeps each file's **relative path** (so `Vol3/P&IDs/sheet-12.pdf` stays distinct from another `sheet-12.pdf`), and shows which are accepted.
2. **Accepted:** PDF. **Skipped, with the reason shown:** anything else (e.g. .dwg, .xlsx, .docx). Never silently dropped.
3. Each file goes **straight from the browser to Cloud Storage** by a signed URL, with a progress bar per file. Large files never pass through our server (Cloud Run caps request bodies at 32 MB).
4. Ingest runs as a background job with progress (files done, pages done). Changes can be checked once ingest finishes.
5. Re-uploading the same file (same content hash) is detected and not ingested twice.

Needed for this to work on Cloud Run (set up in phase 0, `deploy/COMMANDS.md`):
- The runtime service account has `roles/iam.serviceAccountTokenCreator` on itself (signing URLs without a key file).
- The bucket has a CORS rule allowing `PUT` from the service's URL.

## 2. Components and folders

The single source of the repo layout. Phase 0 creates all of it (empty packages where the code comes later).

```
INTERLOCK/
├── .venv/                 local virtual environment (git-ignored, created in phase 0)
├── app/
│   ├── __init__.py
│   ├── config.py          settings from environment variables; never exposes the key
│   ├── api/               FastAPI app and routes
│   ├── ingest/            files to pages
│   ├── reading/           steps 1-5
│   ├── drawing/           step 6
│   ├── rules/             step 7 + rules.yaml
│   ├── register/          step 7b
│   ├── explain/           step 8
│   ├── verdict/           step 9
│   ├── agent/             steps 10-11
│   ├── jobs/              background jobs
│   └── store/             Firestore + Cloud Storage
├── web/                   the one screen (index.html + assets)
├── tests/
│   └── rules/             mirrors every RULES.md test case
├── eval/
│   ├── keys/              answer keys, committed before their runs
│   ├── baselines/         keyword, one-call, one-call-math scripts
│   └── results/           raw run outputs, small JSON, committed as evidence
├── data/                  local copies of test PDFs (git-ignored)
├── scripts/               check_models.py, find_pages.py, label_positions.py, local ingest, eval runner
├── deploy/
│   └── COMMANDS.md        gcloud commands Bhargavi runs
├── docs/
│   ├── PROJECT.md  ARCHITECTURE.md  RULES.md  EVAL.md  PHASES.md
│   └── specs/             PHASE_N.md, one per phase
├── CLAUDE.md
├── README.md
├── Dockerfile
├── .dockerignore
├── requirements.txt       pinned versions
├── pytest.ini             pythonpath = . so tests import app
├── .gcloudignore          keeps .env, .venv, data, PDFs out of the deploy upload
├── .gitattributes         LF line endings (files run in Linux)
├── .gitignore
└── .env.example           names only (.env is git-ignored)
```


| Path | Component | Uses a model? | Notes |
|---|---|---|---|
| `app/ingest/` | Files to pages: text per page (with word positions), PNG for drawing pages, drawing detection, content hash | No | PyMuPDF. Drawings = large sheets or near-empty text layer; other page images on demand |
| `app/reading/` | Steps 1-5 | Yes | Every value carries `page`, `quote`, `unit`; design-basis limits too (`RULES.md`). Extraction uses structured outputs (response schema), never hand-parsed JSON |
| `app/drawing/` | Step 6 | Yes (Argon, image) | `locate` finds the item's printed label in the text layer and crops around it; Argon boxes the item and reads line size, role and shared header from the image; `verify` (code) accepts a reading only if its box holds the printed label in the text layer (`RULES.md`, Drawing values). No text layer: nothing reaches the rules |
| `app/rules/` | Step 7, rule engine; `rules.yaml` mirrors `RULES.md` | **Never** | |
| `app/register/` | Step 7b, register clash check | No | Firestore is the only source of truth |
| `app/explain/` | Step 8 | Yes (Carbon) | Explains; never changes a status |
| `app/verdict/` | Step 9 | No (Hydrogen writes headlines only) | Pure function of rule results, disagreements, clashes |
| `app/agent/` | Steps 10-11 | Yes (Managed Agent, Neon) | Sandbox per plant; agent config sets `max_total_tokens`; server re-check mandatory |
| `app/jobs/` | Background jobs and progress | No | In-process; state in Firestore |
| `app/store/` | Firestore + Cloud Storage access | No | Backends chosen by `STORE`: `gcp` (default) and `memory` (tests) |
| `app/api/` | HTTP API | No | FastAPI |
| `web/` | One screen | No | Served by the same service |
| `tests/` | pytest; `tests/rules/` mirrors every `RULES.md` test case | | |
| `eval/keys/` | Answer keys, committed **before** the runs they score | | |
| `eval/baselines/` | Keyword, one-call, one-call-math scripts | | |
| `eval/results/` | Raw run outputs (small JSON, committed). The results table itself lives only in `EVAL.md` §5 | | |
| `scripts/` | `check_models.py`, ingest of a local folder, eval runner | | |
| `Dockerfile` | Repo root | | |

## 3. Which model does what

Model strings come from the hackathon builder resources and live only in environment variables (`MODEL_*`), never in code.

| Model | Job | Why this model |
|---|---|---|
| **Gemini 4 Hydrogen** | One-line headline per finding on the screen | Fast, cheap workhorse |
| **Gemini 4 Argon** | Long read over the plant's pages; pulling values; reading the P&ID image | Long context, strong vision |
| **Gemini 4 Carbon** | Which disagreeing page is likely right; what goes wrong in the plant | Strongest reasoning; used once per change |
| **Gemini 4 Neon** | Understanding the change (step 1); the Managed Agent's model (step 10) | Near-Carbon quality, fast, strong at code |
| **Decisions API** | "Is this page about the same item as the change?" with a probability; threshold chosen on Set A, applied unchanged to Set E (`EVAL.md`) | Narrow, measurable job |

**How models are called** (hackathon builder guide, `google-genai` >= 3.2.0):

- **Model calls:** `client.interactions.create(model=..., input=..., generation_config={"thinking_level": ...})`. Plain text on the stable client; **structured output only on the v1beta client** (the stable API rejects `response_mime_type`: live error, 21 Nov). Thinking levels: Neon and Hydrogen `low` / `medium` / `high` (default) / `xhigh`; Carbon and Argon `low` / `medium` (default) / `high`. **Never** pass temperature, top_p, top_k, a thinking budget, or `"minimal"`.
- **Structured outputs:** every extraction uses a response schema; JSON is never hand-parsed.
- **Decisions API:** v1beta client, `decisions.create(model=..., input=[text and image parts], questions={...})`. Question types `noul` (P(yes), 0.01-0.99, plus confidence), `choice` (keys sort alphabetically; always include an explicit `"other"` key) and `score`. Max input 262,144 tokens per call.
- **Managed Agent:** v1beta client, `interactions.create(agent=..., environment="remote", agent_config={"type": "antigravity", "model": <Neon>, "max_total_tokens": ...}, input=...)`. Returns `environment_id` and `output_text`. The plant's sandbox is reused with `environment=<environment_id>` and `previous_interaction_id=<id>`.

**Decisions API fallback:** if the same-item job is not working by the phase 2 cut-line, it moves to ranking flagged results by severity. It never leaves the product.

## 4. Size limit

Argon's input limit is 1,048,576 tokens. Before the long read, count tokens. **Today:** a plant over the limit gets a clear message ("this set is N tokens, over the 1,048,576 limit; splitting is not available yet") and code search still runs over every page. BHEL (851 pages) is under the limit. Splitting large sets is future work.

## 5. Data

| Store | What |
|---|---|
| Cloud Storage `plants/{plant_id}/files/` | Uploaded PDFs |
| Cloud Storage `plants/{plant_id}/pages/{n}.json` and `{n}.png` | Page text with word positions; PNG for drawing pages only (too large for Firestore's 1 MiB document limit) |
| Cloud Storage `plants/{plant_id}/changes/{change_id}/drawing.png` | Highlighted drawing |
| Firestore `plants/{plant_id}` | Name, files (relative path, size, hash, status), page count, ingest status, agent sandbox id (`environment_id`) and last interaction id |
| Firestore `plants/{plant_id}/changes/{change_id}` | Change text, found pages, values with quotes, rule results, verdict |
| Firestore `plants/{plant_id}/register/{entry_id}` | Approved changes. **Only source of truth.** The agent sandbox gets a read-only copy per run |
| Firestore `jobs/{id}` | Job type, state, progress, steps with seconds, result |
| Firestore `change_index/{change_id}` | `plant_id`, so `/changes/{id}` needs no plant id |

Every value record: `{item, attribute, value, unit, source, file, page, quote, evidence_ok}`. `source` is `document`, `change` or `fix` (`RULES.md`, Inputs).

One path scheme everywhere: `plants/{plant_id}/changes/{change_id}`, in Firestore and in Cloud Storage. Change ids are globally unique, so the API can use `/changes/{id}` without the plant id.

## 6. API

| Method | Path | Does |
|---|---|---|
| POST | `/plants` | Create a plant |
| POST | `/plants/{id}/files` | Takes `[{relative_path, size, content_hash}]`; returns a signed upload URL per accepted file and the skipped files with reasons |
| POST | `/plants/{id}/ingest` | Ingest the uploaded batch; returns a job id |
| GET | `/plants/{id}` | Plant, files, ingest status, page count |
| POST | `/plants/{id}/changes` | Check a change (steps 1-9); returns a job id |
| GET | `/jobs/{id}` | Progress and result of any job |
| GET | `/changes/{id}` | Result: pages, values, rule results, verdict, drawing image |
| POST | `/changes/{id}/fix` | Start the agent (steps 10-11); returns a job id |
| POST | `/changes/{id}/approve` | Server re-check, then add to the register |
| GET | `/plants/{id}/register` | Approved changes |
| GET | `/health` | Liveness |

## 7. Deployment (production)

- **Cloud Run**, one service: API + `web/`. Region `us-central1`.
- Flags: `--timeout=900 --memory=2Gi --cpu=2 --min-instances=1 --max-instances=1 --no-cpu-throttling` (background jobs run in-process, so today there is exactly one instance).
- **Your own GCP project**, not the temporary hackathon account (deleted tonight).
- **Secret Manager** holds `GEMINI_API_KEY` and `ACCESS_CODE`. Bhargavi creates the secrets herself; Claude Code never sees the key.
- **Caching:** Gemini 4 caches automatically on prompts of 4,096+ tokens; the plant's pages are the identical first block of every long read so the cache is reused. No manual caching calls.
- Deploy: `gcloud run deploy --source .` in a second terminal while coding continues; deploy after phases 0, 2, 3, 4 and 6. Each deploy sets `APP_VERSION` to the git short sha (shown by `/health`); exact commands in `deploy/COMMANDS.md`.
- **After the event:** the hackathon key, Gemini 4 access, the Decisions API and agent sandboxes may stop working when the temporary account is deleted. The register and all results survive in Firestore; sandboxes are recreated on first use with a new key.

## 8. Security

- No key in code, logs, commits or the browser. `.env` is git-ignored; `.env.example` holds names only. Claude Code is not given the key.
- Model output is data. It never runs as code on our server. Only the agent runs code, inside Google's sandbox.
- The agent cannot change the rules or the register: the server re-runs both on every fix before showing "proven".
- Access to the live product: one shared access code (`ACCESS_CODE`). No accounts today.
