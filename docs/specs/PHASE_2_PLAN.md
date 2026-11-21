# Phase 2 — build plan (for approval)

Implements `docs/specs/PHASE_2.md` **with its Amendments** (they override). **Approved 21 Nov** with four changes that override the steps below:
1. `scripts/ingest_local.py` dropped: `run_change.py` uses the plant from the live upload. C6 screen is minimal: verdict banner plus plain sections from the result JSON. C4 starts while Bhargavi deploys and uploads.
2. Ingest also writes `plants/{id}/pages_all.json`: every page's `{n, file, page, text}` in `n` order. The pipeline reads that one file and caches it in memory per plant. Per-page JSON/PNG stay for phase 3. Test: `pages_all.json` order equals `n` order.
3. The N in "No conflicts found in N pages checked" comes from the plant's `page_count` in the result, never computed in the browser.
4. The long-read prompt is built from `pages_all.json`, so it is byte-identical across runs (automatic cache). Every step ends in a commit with `pytest -q` green. Claude Code never runs anything that needs the Gemini key; Bhargavi runs every live call and pastes back only printed output.

Clock: starts ~13:00. **Deploy 1 by 13:20. Cut-line 14:00.** Anything not working at 14:00 moves to the first 15 minutes of phase 3; the drawing starts by 14:30.

Checked in the installed SDK (not guessed): structured output = `interactions.create(..., response_format=<JSON schema>, response_mime_type="application/json")`; tokens = `client.models.count_tokens`; Decisions and Managed Agent on the v1beta client (ARCHITECTURE §3).

---

## 0. Gates (checked before any run command is given)

| Gate | State now |
|---|---|
| A1-A3 committed | ✅ `96ae8cb` 12:44, A2 corrected `5859356` |
| E1-E5 committed | ✅ `2ebad3c` 12:47 |
| Before giving Bhargavi a run command | `git log -- eval/keys` is shown; no command if a key is missing |

## 1. Step P1 — Store, access, upload API, ingest, minimal page → **deploy 1 by 13:20** (commits C1-C3)

### C1 `phase 2: store (memory, gcp) and access code` (~10 min)
- `app/config.py`: `STORE` (default `gcp`), `get_access_code()`.
- `app/api/access.py`: dependency on `/plants`, `/changes`, `/jobs`: `X-Access-Code` vs `ACCESS_CODE` with `hmac.compare_digest`; missing/wrong → 401 `{"detail": "access code required"}`; unset → 503 "access code not configured". Never logged.
- `app/store/base.py`: `Store` protocol — plants (create/get/update, add files), pages (put/get text JSON, put PNG), changes (put/get, `change_index`), jobs (create/update/get, list unfinished), register (list entries for a plant), blobs (exists, download to temp), `signed_put_url(path)`.
- `app/store/memory.py`: dicts; `signed_put_url` returns a fake URL (tests only).
- `app/store/gcp.py`: Firestore + Cloud Storage per ARCHITECTURE §5. Signed URL: `blob.generate_signed_url(version="v4", method="PUT", content_type="application/pdf", expiration=30 min, service_account_email=<runtime SA>, access_token=<ADC token>)` — signs through IAM signBlob (no key file; phase 0 `serviceAccountTokenCreator`). Firestore field > 900 KB → GCS `result.json` + pointer.
- `get_store()` picks the backend from `STORE`.
- Tests: `test_access.py` (401 / 401 wrong / 503 unset / `/health` open), `test_store_memory.py`.

### C2 `phase 2: upload API and ingest job` (~15 min)
- `app/api/main.py` routes: `POST /plants`, `POST /plants/{id}/files`, `POST /plants/{id}/ingest`, `GET /plants/{id}`, `GET /jobs/{id}`.
- `/files`: accepted `.pdf` (any case) size > 0; skipped with reason: other extension ("not a PDF: .dwg"), size 0 ("empty file"), `..` or leading `/` ("unsafe path"); duplicate `content_hash` in the plant → `duplicates`. File entry `status: "uploading"`.
- `app/jobs/runner.py`: thread pool (2 workers), job state in the store after every step; on startup unfinished jobs → `failed` ("server restarted").
- `app/ingest/ingest.py`: per file: download to `/tmp`, PyMuPDF; per page: text, words normalised 0-1, `is_drawing` (longer side > 600 mm **or** < 200 chars, both from `reading.yaml`), PNG 150 dpi for drawing pages only; global `n` in sorted relative-path order, `{file, page}` kept; progress every 10 pages; broken PDF fails that file only (exception class name); delete `/tmp` copy; at the end `page_count`, `ingest_status: done`, token count (§3, C5 adds the real count; C2 stores characters ÷ 4 marked "estimated").
- `app/reading/reading.yaml`: drawing thresholds, evidence word fraction 0.9, same-item threshold 0.5, min_confidence 0.6, `same_item_mode: decisions`, thinking levels all `low`.
- Tests: `test_upload_api.py` (accept/skip/unsafe/duplicate/`A/s.pdf` vs `B/s.pdf`), `test_ingest.py` (3-page PDF made in the test, one A1-size page → 1 drawing + PNG, words 0-1; corrupt PDF fails that file only).

### C3 `phase 2: minimal upload page` (~10 min) → **deploy 1**
- `web/index.html` + `app.js` + `app.css`, plain: access code prompt (`sessionStorage`; 401 clears it), create/pick plant (`localStorage` id), drop zone + "Choose folder" (`webkitdirectory`) + "Choose files"; folder drag walks `webkitGetAsEntry()`; list every file accepted / skipped (reason) / duplicate; SHA-256 via `crypto.subtle`; PUT with `XMLHttpRequest` (progress bar), exactly `Content-Type: application/pdf`, no access-code header, 3 at a time, one retry; then `/ingest` and poll the job every 2 s (files done, pages done).
- Serve `web/` statics from FastAPI.
- **Bhargavi:** deploy (COMMANDS.md block 6; no new env var: `STORE` defaults to `gcp`); on the live URL upload `data\bhel` as a folder, then a new plant with the 5 files picked; both must say **851 pages**; drop a non-PDF in the folder to see it skipped.

## 2. Step P2 — Code-only reading pieces (commit C4, ~15 min, no model)

- `app/reading/search.py`: every page, case-insensitive, spaces and hyphens ignored; names + item + system; same-page `unit_tag` (spaces ignored) or page section title, else tagged `other-unit look-alike`.
- `app/reading/evidence.py`: NFKC, lower, collapse whitespace, unify dashes/quotes; quote substring of page **or** (table rows) every number on the page and ≥ `reading.yaml` fraction of word tokens; value in quote (numbers as numbers; counts: digits); unit known via `units.to_base` or an empty-unit input. Fail → `evidence_ok=False` + reason. Applies to values and limits (limit: low and high both in the quote).
- `app/reading/scenario.py`: merge checked values per input (same value → one, cite first, list all; different → `Disputed` and, when the change touches the input or `working` vs `arrangement` differ, a disagreement); register overlay (source `register`, empty now); issued vs after-change (change values replace, source `change`); mapping per Amendments (R1 `pumps_into_line` only from a checked `shared_discharge`, else missing → held with the A1 message; R3 `q_out` = per-pump flow × working); R1-R3 always for pump items; `run_rules(live_only=True)` both sets.
- `app/register/clash.py`: same item (normalised item or shared name) + same attribute, approved ≠ after-change value, or the change undoes it → `[{entry_id, attribute, approved, proposed}]`.
- Tests: `test_search.py`, `test_evidence.py` (spec §10 list), `test_scenario.py` (**200 NB demo**: with fake checked `shared_discharge` true → R1 1.86 OK + note; absent → held with the A1 message; disagreement; R2 flagged; R3 held; verdict BLOCK; register overlay replaces an issued value), `test_clash.py`.

## 3. Step P3 — Model steps (commit C5, ~20 min)

- `app/reading/models.py`: the only Gemini caller. `call(role, prompt, schema=None, thinking=...)` → stable client `interactions.create(model=MODEL_<role>, input, generation_config={"thinking_level"}, response_format, response_mime_type)`; `decide(questions, input)` → v1beta `decisions.create`; `count_tokens`. Timeout per call; one retry on 429/5xx after 2 s; logs model role, seconds, token count — never content, never the key. No temperature/top_p/top_k/budget/"minimal".
- `schemas.py`: understanding (with `changes[].input` enum = engine input names), long-read pages, values+limits+shared_discharge, explanations, headlines.
- `understand.py` (Neon, low), `longread.py` (token count; over 1,048,576 → skip with the ARCHITECTURE §4 message; Argon low; prompt = pages block first in `n` order, then the **raw change text**), `sameitem.py` (Decisions `noul` per candidate, batched < 262,144 tokens; threshold / uncertain from `reading.yaml`; fallback names + unit tag, logged), `values.py` (Argon low; kept pages + top 5 "velocity … m/s" design-basis pages; copy as printed, counts as digits in the quote, never compute or convert).
- `scripts/ingest_local.py` (ingest `data/bhel` into the gcp store with ADC; no Gemini key) and `scripts/run_change.py "<change>" --plant <id>` (prints pages, values with evidence, results issued/after, verdict, **seconds per step**).
- Tests: `test_pipeline_fakes.py` part 1 (fake `models.py`: understanding → search → same-item → values → evidence → scenario), Decisions failure → names mode recorded; over-limit → long read skipped.
- **Bhargavi:** `gcloud auth application-default login` once; `python scripts/run_change.py "<A1 change>" --plant <id from the live upload>`; paste the output. She checks every page and value against the PDF.

## 4. Step P4 — Explain, headlines, pipeline job, result screen → **deploy 2** (commit C6, ~15 min)

- `explain/carbon.py` (Carbon low, only with disagreements; failure → "explanation unavailable") and `explain/headlines.py` (Hydrogen low; failure → rule messages) **in parallel**.
- `reading/pipeline.py`: steps with `steps[]` {name, state, seconds}: understand ‖ long read (parallel) → search → same-item → values → evidence → scenario+rules → clash → explain ‖ headlines → verdict. Result per spec §8 (no "as issued" named finding).
- Routes: `POST /plants/{id}/changes` (409 if ingest not done) → `{job_id, change_id}`; `GET /changes/{id}` via `change_index`.
- Screen (plain, last): change box + Check; step list with seconds; verdict banner (BLOCK red / REVIEW amber / "No conflicts found in N pages checked" neutral); headlines; pages; values (failed evidence struck through with reason); disagreements + Carbon note; calc sheet (issued and after per rule: status, value, limit, source, formula, inputs with citations, assumptions, notes); clashes; "Drawing (phase 3)" placeholder.
- Tests: `test_pipeline_fakes.py` part 2 (step order, Carbon failure → verdict unchanged), `test_no_key_in_logs.py` (dummy key never in any log record).
- **Bhargavi:** deploy 2; run A1-A3 on the live URL; time one change from Check to verdict.

## 5. Step P5 — Tune on set A only (commit per change)

Raise a thinking level, add names, or move the same-item threshold only if A1-A3 miss key pages or values; each change and its reason in the commit message; the threshold and set A precision/recall go to `EVAL.md` §5 only (phase 5).

## 6. Done-when (how it is checked)

| Check | Evidence |
|---|---|
| Keys before runs | `git log -- eval/keys` times vs first run output time |
| Folder **and** files upload on the live URL; 851 pages each; non-PDF skipped with reason | Bhargavi's screenshot/paste of both plants |
| A1-A3 return every key page and the right values | Bhargavi's confirmation per key; misses → `EVAL.md` §6 |
| Every value's quote passes evidence or is struck through with reason | result JSON |
| Verdict < 90 s on the live URL | seconds per step from the result; total in the commit message |
| Floor-wash change: disagreement + BLOCK | result JSON / screen |
| `pytest -q` green; no key in code, logs, commits; Status `done (phase-2-reading)`; tag; deployed `/health` = tag sha | outputs |

## 7. Risks and responses

| Risk | Response |
|---|---|
| Signed URL fails on Cloud Run (signBlob permission) | error class shown on the page; check `serviceAccountTokenCreator` and `iamcredentials` (both set in phase 0) |
| Ingest > 5 min for 851 pages | commit records the measured time; drawing PNGs only for drawing pages already limits it |
| Change check > 90 s | seconds per step show the slow step; first fix is parallelism already planned, then fewer design-basis pages |
| Decisions API fails | names fallback, recorded in the result (cut-line 13:45 in `PHASES.md`) |
| A1 recall low (abbreviations "FLR WASH WTR", scope "WASTE WATER") | tune Neon names on set A (dev set), recorded |
| 14:00 reached | stop, list what works, move the rest to phase 3's first 15 minutes |

## 8. Approve

Reply "approved" (or changes). I start at C1.
