# Phase 2 spec — Upload and reading

**The Amendments section at the end overrides the text above it.**

Owner docs: `ARCHITECTURE.md` §1, §1a, §3, §4, §5, §6, §7, §8 (flow, upload, model jobs, size limit, data, API, deployment, security), `RULES.md` (inputs, verdict), `EVAL.md` §1-§2 (keys before runs), `PHASES.md` (phase 2), `CLAUDE.md`. Engine contract: `docs/specs/PHASE_1.md` §1-§2 and its Amendments. Time: 12:50-14:15 (lunch 13:00 while things run).

## Goal

On the live URL an engineer uploads the BHEL set (a folder or individual files), it ingests to 851 pages, they type a change, and within 90 s they see: the pages about that item with exact quotes, the values with their sources, R1-R3 results (OK / flagged / held), any documents that disagree, a register clash check, and the verdict. Steps 0-9 of `ARCHITECTURE.md` §1, except step 6 (drawing, phase 3).

## Gates (before anything runs on BHEL)

- **Set A keys** (`eval/keys/A1-A3.json`) committed before the first change is run through the pipeline, live or local.
- **Set E keys** (≥3, `eval/keys/E*.json`) committed before any set E change is run. Carried from phase 0.
- Claude Code checks `git log -- eval/keys` before giving Bhargavi any run command, and refuses to give one if the key is missing.

## The key rule for this phase

Claude Code never runs anything that needs the Gemini key (CLAUDE.md). It writes the code, the unit tests with fakes, and the exact commands; **Bhargavi runs every live model call** (local script or the live URL) and pastes back only the printed output.

---

## 1. Files

```
app/
├── config.py            + get_access_code(); nothing else changes
├── api/
│   ├── main.py          routes from ARCHITECTURE §6 for phase 2 (list below); access-code dependency
│   └── access.py        X-Access-Code check (hmac.compare_digest)
├── store/
│   ├── base.py          Store interface (plants, files, pages, changes, jobs, register)
│   ├── gcp.py           Firestore + Cloud Storage (+ v4 signed upload URLs)
│   ├── local.py         same interface on the local disk under cache/ (git-ignored), for local runs
│   └── memory.py        same interface in memory, for tests
├── ingest/
│   └── ingest.py        PDF -> pages (text JSON per page; PNG for drawing pages); content hash; skip list
├── jobs/
│   └── runner.py        in-process background jobs (thread pool, 2 workers); progress in store
├── reading/
│   ├── models.py        the only place that calls Gemini (stable + v1beta clients); retries; timings
│   ├── schemas.py       response schemas for every structured output
│   ├── understand.py    step 1, Neon
│   ├── search.py        step 2, code search (no model)
│   ├── longread.py      step 2, token count + Argon long read
│   ├── sameitem.py      step 3, Decisions API (fallback: name match)
│   ├── values.py        step 4, Argon structured values + document limits
│   ├── evidence.py      step 5, evidence check (no model)
│   ├── scenario.py      issued vs after-change inputs for R1-R3, disagreements (no model)
│   ├── pipeline.py      steps 1-9 in order, progress per step, writes the change result
│   └── reading.yaml     thresholds and thinking levels (not engineering limits)
├── register/
│   └── clash.py         step 7b, clash check against the register (no model)
├── explain/
│   ├── carbon.py        step 8, only when documents disagree
│   └── headlines.py     step 9 headlines, Hydrogen
web/
└── index.html (+ app.js, app.css)   the one screen; no framework, no build step
scripts/
├── ingest_local.py      ingest data/bhel/*.pdf into the local store (Bhargavi runs; no key needed)
└── run_change.py        run one change through the pipeline on the local store, print the result and timings (Bhargavi runs; needs key)
tests/
├── test_access.py  test_store_memory.py  test_ingest.py  test_upload_api.py
├── test_search.py  test_evidence.py  test_scenario.py  test_clash.py
├── test_pipeline_fakes.py   whole pipeline with a fake models.py (no network)
└── test_no_key_in_logs.py
```

`requirements.txt`: no new libraries unless needed; if `google-auth` must be listed explicitly for signing, pin it and add to README "Libraries".

## 2. Access code

- Every route under `/plants`, `/changes`, `/jobs` requires header `X-Access-Code` equal to `ACCESS_CODE` (constant-time compare). Wrong or missing → 401 with `{"detail": "access code required"}`. `/health` and `/` stay open.
- `ACCESS_CODE` unset → every protected route returns 503 "access code not configured" (never open by default).
- The page asks for the code once and keeps it in `sessionStorage`; a 401 clears it and asks again.
- Never logged, never echoed.

## 3. Store (`app/store/`)

One interface, three backends chosen by `STORE` env var: `gcp` (default in Cloud Run), `local` (scripts), `memory` (tests). Add `STORE` to `.env.example` and `config.py` (default `gcp`). Bhargavi adds `STORE=local` to her own `.env` for the local scripts; the deploy command needs no change because the default is `gcp`.

Layout exactly as `ARCHITECTURE.md` §5:
- GCS `plants/{plant_id}/files/{relative_path}` (PDFs), `plants/{plant_id}/pages/{n}.json` (`{"file", "page", "n", "text", "width", "height", "is_drawing"}`), `plants/{plant_id}/pages/{n}.png` (drawing pages only).
- Firestore `plants/{plant_id}`: `name, created_at, files[{relative_path, size, content_hash, status, pages, skipped_reason}], page_count, ingest_status, token_count`; agent fields stay empty until phase 4.
- Firestore `plants/{plant_id}/changes/{change_id}`: change result (§8). Firestore `plants/{plant_id}/register/{entry_id}`: read in this phase (clash check), written in phase 4.
- Firestore `jobs/{id}`: `{type, plant_id, change_id?, state: queued|running|done|failed, step, progress: {done, total}, steps: [{name, state, seconds}], error, created_at, updated_at}`.
- `n` is the page's global index in the plant (files in sorted relative-path order, pages in order). Every page also keeps `file` (relative path) and `page` (1-based in that file): **all citations use `{file, page}`**, never `n`.
- Ids: `uuid4().hex[:12]`; change ids unique globally (`/changes/{id}` needs no plant id). `gcp.py` keeps a Firestore doc `change_index/{change_id} -> plant_id`.

## 4. Upload (`ARCHITECTURE.md` §1a)

**API**
- `POST /plants` `{name}` → `{plant_id}`.
- `POST /plants/{id}/files` `[{relative_path, size, content_hash, content_type}]` → `{"accepted": [{relative_path, upload_url}], "skipped": [{relative_path, reason}], "duplicates": [{relative_path}]}`.
  - Accepted: `.pdf` (case-insensitive) with size > 0. Skipped with reason: any other extension ("not a PDF: .dwg"), size 0 ("empty file"), a relative path with `..` or starting with `/` ("unsafe path").
  - Duplicate: a file with the same `content_hash` already in the plant → not uploaded again, listed as duplicate.
  - Signed URL: v4, method PUT, content type `application/pdf`, 30 minutes, signed through the IAM signBlob API with the runtime service account (no key file; the `serviceAccountTokenCreator` role from phase 0). The file's Firestore entry is created with `status: "uploading"`.
- `POST /plants/{id}/ingest` → `{job_id}`. Ingests every file with `status` "uploading" whose object now exists in GCS (others marked "missing").
- `GET /plants/{id}` → plant doc (no page texts).

**Page**
- One drop zone + two buttons: "Choose folder" (`<input type=file webkitdirectory multiple>`) and "Choose files" (`<input type=file multiple>`). Drag and drop accepts folders (walk `webkitGetAsEntry()` recursively) and files.
- The list shows every file with its relative path: accepted / skipped (with reason) / duplicate. Nothing silently dropped.
- SHA-256 per file in the browser (`crypto.subtle.digest`), then PUT straight to the signed URL with `XMLHttpRequest` for a per-file progress bar; 3 uploads at a time; one retry on failure; a failed file is shown as failed.
- The PUT to Cloud Storage sends exactly `Content-Type: application/pdf` (it must match the signature) and **no** `X-Access-Code` header (the bucket's CORS allows only `Content-Type`; the code never leaves our own API).
- When all accepted files are uploaded, the page calls `/ingest` and shows the job's progress (files done, pages done). More files can be added later to the same plant (another batch, another ingest).

## 5. Ingest (`app/ingest/ingest.py`, step 0)

Runs as a job. For each new file: download from GCS to `/tmp`, open with PyMuPDF, for each page:
- Text: `page.get_text("text")`, also kept with word positions for phase 3 (`page.get_text("words")` saved in the page JSON as `words: [[x0,y0,x1,y1,text]]` normalised 0-1).
- **Drawing page** if the page's longer side is > 600 mm (A2 and larger) **or** it has fewer than 200 text characters. Thresholds in `reading.yaml`.
- PNG for drawing pages only, 150 dpi (phase 3 boxes it). Other pages get images on demand later.
- Progress after every 10 pages. File status `ingested` with its page count, or `failed` with the exception class name. A broken PDF fails that file, not the job.
- At the end: `page_count`, `ingest_status: done`, and the plant's **token count** for the long read (§6.2), stored on the plant.
- Delete `/tmp` copies as you go (Cloud Run's `/tmp` is memory).

Target: BHEL (851 pages, 118 MB) ingests in under 5 minutes on Cloud Run. If it does not, the commit says the measured time.

## 6. The change check (`app/reading/pipeline.py`, steps 1-9)

`POST /plants/{id}/changes` `{text}` → `{job_id, change_id}`. Refused with 409 if the plant's ingest is not done. The job runs these steps and updates `step` and `steps[]` (name, state, seconds) after each. Model calls go only through `models.py` (one retry on 429/5xx with 2 s backoff, timeout per call, timing logged without content).

**6.1 Understand the change (Neon, thinking `medium`), structured output:**
```
{"item": "SG Unit-1 floor wash water transfer pumps",
 "names": ["floor wash water transfer pump", "FWW pump", "floor wash pump", ...],   // every name/abbreviation the plant may use
 "system": "SG Unit-1 floor wash", "unit_tag": "Unit-1",
 "changes": [{"input": "working", "from": "1", "to": "2", "unit": "count"},
             {"input": "arrangement", "from": "1W+1S", "to": "2W+1S", "unit": ""}],
 "rules": ["R1", "R2", "R3"]}
```
`changes[].input` must be one of the engine's input names (PHASE_1 §2 + Amendments); the schema enumerates them. Each change value becomes `Value(source="change", quote=<change text>)`.

**6.2 Find the item: code search + Argon long read, in parallel.**
- Code search (`search.py`, no model): over every page, case-insensitive, spaces and hyphens ignored, each of `names` plus `item` and `system`. Hits must also contain `unit_tag` (spaces ignored) on the same page **or** within the page's section title, else they are kept as "other-unit look-alike" candidates (the same-item check decides).
- Token count (`longread.py`): count tokens of the long-read prompt with the SDK's count-tokens call for `MODEL_ARGON` (check the exact method with the Gemini docs MCP; if the SDK has none, use characters ÷ 4 and say so in the result as "estimated"). Over 1,048,576 → skip the long read, result says "this set is N tokens, over the 1,048,576 limit; splitting is not available yet; code search only" (`ARCHITECTURE.md` §4).
- Long read (Argon, thinking `low` first; raise only if set A recall needs it): prompt = **the plant's pages block first** (identical every time for the same plant, so the automatic cache is reused: `=== {file} p.{page} ===\n{text}` per page, in `n` order), then the change understanding. Structured output: `[{"file", "page", "why"}]`, pages about this exact item **including** pages that name it differently and P&ID/data-sheet pages for its system.
- Candidates = union of code search hits and long-read pages, deduplicated by `{file, page}`, each tagged with how it was found (`search`, `longread`, `both`).

**6.3 Same item? (Decisions API, `sameitem.py`).**
- One `noul` question per candidate page: "Is this page about {item} ({system}), not a similar item in another unit or system?" Input = the change understanding + the candidate pages' text (each page labelled), batched so each call stays under 262,144 tokens.
- Keep a page if P(yes) ≥ threshold (`reading.yaml`, start 0.5). Confidence below `reading.yaml` `min_confidence` (start 0.6) → keep it, marked `uncertain`, shown as such.
- The threshold is set once on set A (development set) and then frozen for set E (`EVAL.md` §2); the chosen value and its set A precision/recall go to `EVAL.md` §5 only.
- **Fallback** (`reading.yaml` `same_item_mode: names`): keep candidates whose text contains a name plus the unit tag. Used if the Decisions API fails at runtime (logged in the result) or by the 13:45 cut-line decision (`PHASES.md`).

**6.4 Pull the values (Argon, thinking `medium`), structured output.** Input: the kept pages' text (and nothing else). Schema:
```
{"values": [{"input": <enum of engine input names>, "value": "<as printed>", "unit": "<as printed>",
             "file": "...", "page": 12, "quote": "<exact sentence or table row from that page>"}],
 "limits": [{"rule_id": "R1", "name": "velocity_band", "low": 1.8, "high": 2.4, "unit": "m/s",
             "applies_from_nb": 50, "applies_to_nb": 150, "applies_to": "pump discharge",
             "file": "...", "page": 200, "quote": "..."}],
 "shared_discharge": [{"value": true, "file": "...", "page": ..., "quote": "..."}]}
```
- Instructions: every value must be copied from the page as printed, with the quote copied character for character; never compute, never convert units, never guess; if a value is not on the pages, leave it out.
- **Design-basis limits** (e.g. D5-200's velocity table) may sit on pages that are not about the item. So `values.py` also code-searches every page for "velocity" near "m/s" and adds the top 5 such pages to this call's input, marked "design basis".

**6.5 Evidence check (`evidence.py`, no model).** For each value and limit:
1. **Quote on the page:** normalise both (NFKC, lower case, collapse whitespace, unify dashes and quotes). Pass if the normalised quote is a substring of the normalised page text, **or** (for table rows, whose cells extract out of order) every number in the quote appears on the page and ≥ 90% of the quote's word tokens appear on the page.
2. **Value in the quote:** the printed value appears in the quote (numbers compared as numbers: "105.0" = "105"; text compared normalised).
3. **Unit known:** `units.to_base` accepts it, or it is one of the empty-unit inputs (RULES.md Inputs).
- Fail any → `evidence_ok=False` with the reason; the value is shown struck through with the reason and never reaches the rules (the engine treats it as missing → held). Limits with `evidence_ok=False` are ignored (default limit used, and the result says so).

**6.6 Scenario (`scenario.py`, no model).** Builds two input sets for R1-R3 from the checked document values, the change values and the limits:
- **Several pages, same input, same value** (after unit normalisation) → one value (cite the first; list all).
- **Several pages, same input, different values** → `Disputed`, and if the input is one the change touches (`changes[].input`), or `working` vs `arrangement` disagree, also a **disagreement** for the verdict (`{"attribute", "values": [{file, page, value}]}`).
- **Issued** inputs = document values only. **After change** inputs = issued, with each `changes[].input` replaced by the change value (source `change`).
- Mapping for the live rules (documented in the module docstring and tested):
  - R2: `installed` from documents; `working` / `arrangement` from the change when changed; `standby_required` from the arrangement.
  - R1: `flow_per_pump` and line size from documents; `pumps_into_line` = working count **only if** a checked `shared_discharge` value says true; if it says false → 1; if absent → missing (R1 held: "documents do not show whether the pumps share one discharge line"). `service` and `line_role` from documents when found.
  - R3: `volume`, `q_in` from documents; `q_out` = `flow_per_pump` x working count.
- Run `run_rules(..., live_only=True)` on both sets with the checked limits.

**6.7 Register clash (`app/register/clash.py`, step 7b, no model).** Register entries hold `{item, system, attribute, value, unit, approved_at, change_id}`. A clash = an entry for the same item (normalised item or any shared name) and the same attribute whose approved value differs from the after-change value **or** an entry whose approved value the change would undo. Returns `[{"entry_id", "attribute", "approved", "proposed"}]`. Empty register → no clashes (BHEL starts empty; phase 4 writes entries).

**6.8 Explain (Carbon, thinking `medium`), only when there is a disagreement.** One call, structured: `[{"attribute", "likely_right": {file, page}, "why", "consequence"}]`. Text only; it never changes a status, a value or the verdict. If it fails, the result says "explanation unavailable".

**6.9 Verdict and headlines.**
- `verdict(after_results, disagreements, clashes, pages_checked=page_count)`; issued-design results are shown alongside as "as issued" (the 3.71 m/s finding), information for the engineer.
- Headlines (Hydrogen, thinking `low`): one line per flagged/held result and per disagreement, from the result's own message; on failure, the rule message is the headline.

## 7. Jobs (`app/jobs/runner.py`)

- In-process thread pool (2 workers; Cloud Run has `--no-cpu-throttling`, one instance). State in the store after every step.
- On startup, any job still `queued`/`running` is marked `failed` ("server restarted"); the page offers "run again".
- `GET /jobs/{id}` → the job doc; the page polls every 2 s.

## 8. Change result (`GET /changes/{id}`)

```
{"change_id", "plant_id", "text", "understanding", "seconds_total", "steps": [...],
 "token_count": N, "long_read": "done" | "skipped: over limit" | "failed",
 "same_item_mode": "decisions" | "names",
 "pages": [{"file", "page", "found_by", "same_item_p", "uncertain", "why"}],
 "values": [{"input", "value", "unit", "file", "page", "quote", "evidence_ok", "evidence_reason"}],
 "limits": [...same shape...],
 "disagreements": [...], "explanations": [...],
 "results_issued": [RuleResult.to_dict()], "results_after": [RuleResult.to_dict()],
 "clashes": [...], "verdict": {...}, "headlines": [...]}
```
Stored in Firestore; any single field over 900 KB is moved to GCS `plants/{plant_id}/changes/{change_id}/result.json` with a pointer.

## 9. The screen (`web/`)

One page, in this order (no tabs, no dashboard):
1. Access code (once). Plant: create or pick the last one (id in `localStorage`).
2. Upload (§4) and ingest progress.
3. Change box + "Check". Progress list of steps with seconds.
4. Result: verdict banner (BLOCK red / REVIEW amber / "No conflicts found in N pages checked" neutral, never green "PASS"), headlines, **pages found** (file, page, why, found by, uncertain), **values** (value, unit, quote, file p.page; failed evidence struck through with reason), **documents that disagree** (+ Carbon note), **calc sheet** (one row per rule, issued and after: status, value, limit, limit source, formula, inputs with citations, assumptions, notes), register clashes. A placeholder box "Drawing (phase 3)".

## 10. Tests (no network; `memory` store; fake `models.py`)

- Access: protected routes 401 without/with wrong code, 503 when unset; `/health` open.
- Upload API: PDF accepted with a URL (fake signer), .dwg/.xlsx skipped with reason, empty file skipped, `../x.pdf` skipped, duplicate hash detected; relative paths kept distinct (`A/s.pdf` vs `B/s.pdf`).
- Ingest: a 3-page PDF made in the test with PyMuPDF (one large-format page) → 3 pages, one drawing page with a PNG, words normalised 0-1; a corrupt PDF fails that file only.
- Search: spacing/hyphen-insensitive hits; unit-tag look-alike tagged.
- Evidence: exact quote passes; table row with cells out of order passes; quote not on page fails; value not in quote fails; "105.0" vs "105" passes; unknown unit fails.
- Scenario: the demo case built from fake checked values (1W+1S on Part1 p.43, 2 working on Part4 p.57, 105 m3/h, 100 NB, shared discharge true, D5-200 bands) → disagreement on working; R1 after 7.43 flagged; issued 3.71 flagged; R2 after flagged (installed 2 < 2+1); R3 held; verdict BLOCK. Shared discharge absent → R1 held.
- Clash: same item and attribute with a different approved value → clash; different item → none.
- Pipeline with fakes: progress steps in order; Decisions failure → falls back to names and says so; long read skipped when token count is over the limit; Carbon failure → "explanation unavailable", verdict unchanged.
- No key in logs: run the pipeline with fakes and a dummy key in the environment; assert the dummy key string is in no log record.
- Existing 220 tests still pass.

## 11. Build order (deploy early: upload only works on the live URL)

1. Store (memory, local, gcp), access code, `/plants`, `/files` with signed URLs, upload page, ingest job. **Deploy (block 6) by ~13:20**; Bhargavi uploads BHEL as a folder and as files on the live URL; ingest must report 851.
2. Search, evidence, scenario, clash (no model) with tests.
3. `models.py`, understand, long read, same-item, values; `run_change.py`. Bhargavi runs A1 locally (`ingest_local.py` once, then `run_change.py`), pastes output.
4. Explain, headlines, pipeline job, `/changes`, `/jobs`, result screen. Deploy again; run A1-A3 on the live URL.
5. Tune only on set A (thinking levels, threshold), every change in the commit message.

Cut order if behind (`PHASES.md`): Carbon explanations → Hydrogen headlines (use rule messages) → Decisions API to severity ranking at the 13:45 cut-line. **Never cut:** folder and file upload, the evidence check, the verdict, the keys-first gates.

## 12. Bhargavi does herself

1. Commit A1-A3 (and E ≥3) before the first run.
2. Deploy (COMMANDS.md block 6) when Claude Code says; add `STORE=gcp` to the deploy env vars only if Claude Code changes the default.
3. On the live URL: upload `data\bhel` as a folder; then a new plant with the 5 files picked individually. Both must say 851 pages.
4. Run each set A change; read every returned page and value against the PDF; tell Claude Code what is right and wrong. Only Bhargavi confirms.
5. Time one change from "Check" to verdict.

## Out of scope

Step 6 drawing (phase 3); the agent, fix, approve and register writes (phase 4); eval runner and baselines (phase 4); R4-R6 live; splitting sets over the token limit; accounts.

## Done when (`PHASES.md` phase 2)

- [ ] A1-A3 committed before their first run (`git log -- eval/keys` times earlier than the first run's output); E ≥3 committed before any E run.
- [ ] On the live URL, BHEL uploads as a folder **and** as individual files; each ingest reports 851 pages; a non-PDF in the folder is listed as skipped with its reason.
- [ ] All three set A changes return every key page and the right values, confirmed by Bhargavi against the pages (misses written to `EVAL.md` §6).
- [ ] Every returned value's quote passes the evidence check, or is shown struck through with the reason.
- [ ] A BHEL change returns a verdict in under 90 s on the live URL (time in the commit message; the number itself goes to `EVAL.md` §5 in phase 5).
- [ ] The floor-wash change shows the scope/data-sheet disagreement and BLOCK.
- [ ] `pytest -q` green; no key in code, logs or commits; `PHASES.md` phase 2 `done (phase-2-reading)`, tag pushed, deployed, `/health` shows the tag's sha.


---

## Amendments (approved 21 Nov; these override the text above)

From the phase 2 review and Bhargavi's decisions. Plan: `docs/specs/PHASE_2_PLAN.md`.

**A1 Shared discharge (R1).** In phase 2 the shared header is not taken from text: with no checked `shared_discharge` value, `pumps_into_line` is missing and R1 is **held** with the message "documents do not state in text whether the pumps share one discharge line". Phase 3 adds drawing evidence: a value read from a P&ID carries `{file, page, box}`, and the code evidence check passes only if the box is on that page and contains the matching text-layer label (e.g. "200NB"). CLAUDE.md and RULES.md get that rule in phase 3, not now. **No values from answer keys in code, ever.**

**A2 Counts.** RULES.md Units: count units `count`, `nos`, `nos.`, `no`, `number` (case and dots ignored). Argon gives a count as the digits printed in the quote (e.g. "2" from "Two (2W) nos."), so the value-in-quote check passes; a count with no digits in its quote is left out.

**A3 Demo scenario test (§10) uses the 200 NB case** from fake checked values: 1W+1S on Part1 p.43; 2 working, 2 installed, 105 m3/h on Part4 p.57; 200 NB; D5-200 bands; change 2W+1S. Expected: disagreement on working/arrangement; R1 after 1.86 m/s OK with the information note **when a checked shared_discharge value is supplied** (test fake), and **held** with the A1 message when it is absent; R2 after flagged (installed 2 < 2 + 1); R3 held; verdict BLOCK (from the disagreement and R2). §6.9: "as issued" results are shown alongside for the engineer, with no named finding.

**A4 Time.** The long read runs on the **raw change text** in parallel with Neon's understanding (it does not wait for it); code search starts when the understanding returns. Carbon and Hydrogen run in parallel. Every model call starts at thinking `low`; a level is raised only if set A needs it, recorded in the commit. Seconds per step are recorded in `steps[]` and printed by `run_change.py`.

**B5 Docs.** `ARCHITECTURE.md`: PNG for drawing pages only (others on demand); Firestore `change_index/{change_id} -> plant_id`; store backends chosen by `STORE`.

**B6 Config.** `config.py` gains `get_access_code()` **and** `STORE` (default `gcp`); `.env.example` gains `STORE`.

**B7 Token count.** Use the installed SDK's `client.models.count_tokens` for `MODEL_ARGON`; if it fails, characters ÷ 4 marked "estimated". (No docs MCP is connected.)

**B8 Thresholds.** The evidence check's word-match fraction (start 0.9) lives in `reading.yaml` with the drawing thresholds, not in Python.

**C9 Note for phase 4.** Approved changes must shape the plant's current state, not only the clash check.

**C (register overlay).** `scenario.py` takes approved register values as an **overlay on the as-issued inputs** (source `register`, citing the entry); empty in phase 2, used in phase 4.

**R2 standby (independent review, 21 Nov; overrides §6.6).** `standby_required` comes only from the documents' arrangement or the default, never from the change: a changed arrangement sets only the working count.

**Service (independent review, 21 Nov; overrides §6.6).** `service` comes only from the data sheet's "Fluid to be handled" value, quoted; never from the item name. The values prompt says so, and `scenario.py` drops any service value whose quote lacks "Fluid to be handled" (marker in `reading.yaml`).

**Arrangement text.** `parse_arrangement` searches anywhere in the text, first match wins: "Two (1W+1S) nos." → 1W+1S; "(2W)" → 2W; "3X100%" → installed 3, working 1, standby 2.

**C11 Rules per item.** For pump items, R1-R3 always run; Neon's `rules` list is ignored for them (a rule with nothing to check comes back held, visibly).

**Trims.**
- `app/store/local.py` dropped. Backends: `gcp` and `memory`. `scripts/ingest_local.py` and `scripts/run_change.py` use the **gcp store with Bhargavi's ADC login** (`gcloud auth application-default login`); "local" means the code runs on her laptop, the data lives in her project.
- The screen is built **last and plain**: it shows the change result clearly; polish waits for phase 6.
- **Phase 2 cut-line 14:00:** anything not working then moves to the first 15 minutes of phase 3; the drawing starts by 14:30.

**Build order** (replaces §11): 1 store (memory, gcp), access code, `/plants`, `/files`, ingest job, minimal upload page → deploy by ~13:20; 2 search, evidence, scenario, clash with tests; 3 `models.py`, understand, long read, same-item, values, `run_change.py`; 4 explain, headlines, pipeline job, `/changes`, `/jobs`, result screen (plain) → deploy; 5 tune on set A only.
