# Phases

Build order for 21 Nov 2026. A phase is done only when its check passes. **Submit by 16:45** (deadline 17:00).

Each phase has a **Status** line: `not started` / `in progress` / `done (tag)`. Claude Code works only on the phase marked `in progress`.

---

## End of every phase (5 minutes)

1. Tests pass.
2. Docs match the code: anything that changed is updated in the doc that owns it.
3. Commit, then tag `phase-N-name`. Set the phase's Status to `done (tag)`.
4. After phases 0, 2, 3, 4 and 6: deploy in a second terminal (`gcloud run deploy --source .`) and keep coding; check `/health` on the live URL at the start of the next phase.

---

## Phase 0 — Setup, production skeleton, unseen changes (11:30-12:10)

Status: done (phase-0-setup) — open item: set E keys (≥3), due before phase 2 runs anything. Evidence: live `/health` returned version `54c95db` (12:16); `check_models.py` 6 of 6 answered.

Detailed spec: `docs/specs/PHASE_0.md`.

**Build (Claude Code):** git repo; folder structure as in `ARCHITECTURE.md` §2; `.gitignore`, `.env.example`; FastAPI app with `/health` and one placeholder page served from `web/`; Dockerfile; `scripts/check_models.py` (calls each `MODEL_*` once, prints answered / failed); the exact gcloud commands for Bhargavi to run.

**Bhargavi does herself (Claude Code never sees the key):**
- Puts the hackathon key and the model strings from the builder resources into `.env`.
- Creates the Secret Manager secrets, the bucket, Firestore, and the Cloud Run service on her own GCP project.
- Runs `scripts/check_models.py` in her own terminal.

**In parallel (15 minutes, the unseen test):** ask 3-5 people here to each write one change to the BHEL plant (show them the pump list on the scope page). With each author, write the expected pages and values. Commit them to `eval/keys/E*.json` (format: `EVAL.md` §2) **before any system runs on them.**

**Done when:**
- The live Cloud Run URL shows the page and `/health` returns OK.
- `check_models.py` gets an answer from Hydrogen, Argon, Carbon and Neon, the Decisions API answers one test question, and the Managed Agent completes one trivial task.
- At least 3 set E keys are committed.
- `git grep` for the key's prefix returns nothing.

**Cut-line 12:05:** if Cloud Run fails, fix it before anything else. A demo that only works on a laptop fails the production goal.

## Phase 1 — Rule engine (12:10-12:50)

Status: done (phase-1-rules). Evidence: `pytest -q` 220 passed; CONFIRM values recorded (`rules.yaml` all `confirm: false`); keys A1-A3, B1-B5, F1-F3 committed 12:44 (`96ae8cb`).

Detailed spec: `docs/specs/PHASE_1.md` (with its Amendments); plan: `docs/specs/PHASE_1_PLAN.md`.

**Build:** `app/rules/` with R1-R6 from `RULES.md`; units; OK / flagged / held; `app/verdict/` with `verdict()` (including the register clash input) and `proven()`; `scripts/find_pages.py` and `scripts/label_positions.py` for writing keys A and B.

**Done when:**
- Every test case in `RULES.md` passes in `tests/rules/`.
- A test checks `rules.yaml` matches `RULES.md` (rule ids and limits).
- Bhargavi has confirmed or corrected every **CONFIRM** value, recorded in `RULES.md` (confirmed values table).
- Sets A, B and F keys committed (format: `EVAL.md` §2), before phase 2 runs. F: 3 calculations, inputs read from BHEL pages by Bhargavi, worked by hand.

**No model calls in this phase.**

## Phase 2 — Upload and reading (12:50-14:15, lunch at 13:00 while things run)

Status: done (phase-2-reading). Evidence: live uploads as a folder (`5821c37a0d46`) and as individual files (`9eeb30bca0d5`), 851 pages each, a Word file skipped with its reason; A1-A3 run, confirmed by Bhargavi against the PDFs, misses in `EVAL.md` §6; floor-wash change BLOCK with the scope/data-sheet disagreement on the live URL in 39.9 s (cache hit; the plant's first run took 102.1 s, recorded in §6); same-item threshold frozen at 0.25 on set A.

Detailed spec: `docs/specs/PHASE_2.md` (with its Amendments); plan: `docs/specs/PHASE_2_PLAN.md`. **Cut-line 14:00:** anything not working moves to the first 15 minutes of phase 3; the drawing starts by 14:30.

**Build:**
- Upload screen: whole folder or several files, drag or pick; PDFs accepted, others listed as skipped with reason; per-file progress; direct to Cloud Storage by signed URL (IAM role and bucket CORS from `ARCHITECTURE.md` §1a).
- Ingest as a background job with progress.
- Change check as a background job: Neon understands the change; Argon long read + code search; Decisions API same-item check; Argon pulls values and design-basis limits with page, quote, unit; evidence check; rules R1-R3 wired live; register clash check; Carbon explains disagreements; Hydrogen headlines; verdict.
- Token count before the long read; over-limit sets refused with a message.

**Done when:**
- Set E keys (≥3) committed before any change is run on the plant (carried from phase 0).
- The 5 BHEL PDFs upload on the live URL as a folder **and** as individual files, and ingest reports 851 pages.
- All three set A changes return every key page and the right values, confirmed by Bhargavi against the pages.
- Every returned value's quote passes the evidence check.
- A change on BHEL returns a verdict in under 90 s.

**Cut-line 13:45:** if the Decisions API same-item check is not working, use name matching for it and move the Decisions API to severity ranking of flagged results (`ARCHITECTURE.md` §3). Say so in the commit message, and in `EVAL.md` §6 if it changes a result.

## Phase 3 — Drawing (14:15-14:45)

Status: done (phase-3-drawing). Evidence: rotated-page words fixed and tested, BHEL re-ingested live (`9eeb30bca0d5`); box format calibrated on ESP Unit-1 (yx/1000); set B 5/5 (`eval/results/b_141730.json`); A1 live: red box on SG Unit-1 (A4 unit-tag check passed), 5 readings verified against the text layer, R1 after = 1.86 m/s OK under the D5-200 header row 2.4 m/s with the drawing citation, BLOCK, 86.5 s; no-drawing path tested; evidence rule in CLAUDE.md, RULES.md, ARCHITECTURE.md.

Detailed spec: `docs/specs/PHASE_3.md` (with its Amendments); plan: `docs/specs/PHASE_3_PLAN.md`.

**Build:** find the P&ID page(s) for the item; Argon returns a box; draw the red box and values on the image; where a text layer exists, confirm the box lands on the printed label.

**Done when:** set B scored, 5 of 5 or the misses written into `EVAL.md` §6.

**Never cut this phase.** It is the multimodal centre of the demo.

## Phase 4 — Agent and register (14:45-15:45)

Status: done (phase-4-agent). Evidence: eval E×3, A, B, keyword and one-call runs started before the agent work on plant `27d049ccd64f` (keys untouched, register empty), 46/46 done, raw in `eval/results/`; demo plant `9eeb30bca0d5`: the Managed Agent proposed installed 3 in the plant's sandbox and the server re-check marked it **proven** (tries and server stamp shown separately), approved with both disagreements ticked; the second fix reused the same `environment_id` (f810c807…) and listed the earlier run; "remove the third pump" was **BLOCKed** by the register ("clashes with approved change 93a42c41cf6f: installed approved 3, proposed 2"). The impossible change is shown by tests only (D1 (b): R1 held on A1, `EVAL.md` §6). Sandbox has no read-only mounts: bundle integrity by agent-reported sha256; the server re-check decides (`EVAL.md` §6).

Detailed spec: `docs/specs/PHASE_4.md` (with its Amendments M1-M10); plan: `docs/specs/PHASE_4_PLAN.md`.

**First (15 minutes):** eval runner and the keyword and one-call baselines; start sets E, A and B running in the background (`EVAL.md` §1).

**Build:** Managed Agent (Neon) with one persistent sandbox per plant; a read-only copy of the rules and the register per run; fix search, at most 8 tries, propose or refuse; server re-check of rules and register; approve → register in Firestore; progress shown while it runs.

**Done when:**
- Floor-wash change: a fix is proposed and the server re-check marks it proven.
- An impossible change is refused with a reason.
- A second change that clashes with the approved one is BLOCKed by the register check.

**Cut-line 15:20:** if the persistent sandbox fails, run the agent with a fresh sandbox per fix. The register check is server code and stays.

## Phase 5 — Proof (15:45-16:15)

Status: in progress

Detailed spec: `docs/specs/PHASE_5.md` (with its Amendments).

**Build:** collect the background runs started in phase 4; run the one-call-math baseline and set F; time one set-A change by hand; commit raw outputs to `eval/results/`; fill `EVAL.md` §5 and §6.

**Done when:** every cell in `EVAL.md` §5 holds a number from today's runs or "n/a", and each key was committed before its run.

**Also in phase 5 (from the review before phase 4, 21 Nov):**
- **Role-based stricter band (10):** when the line's role is unstated or disputed, use the stricter of the document bands that could apply.
- **"Incomplete" verdict (7d):** a failed values step (or no values at all) gives an explicit incomplete verdict instead of a REVIEW built on nothing.
- **Count next to its marker (7e):** a count must sit next to "nos", "W", "S" or a number word in the quote, not just appear anywhere in it.
- **Cold and warm timing (9):** report both: the first check on a plant (no cache) and a check within a few minutes of another (cache).
- **Guard tests (review item 6):** parse each RULES.md case into inputs, value and status; assert tolerance and live; ban http/subprocess/app.store imports; scan engine.py and verdict.py.
- **`EVAL.md` §6 note (7c):** pages kept only because the same-item confidence was low ("uncertain") and what keeping them costs.

## Phase 6 — Ship (16:15-16:45)

Status: not started

**Build:** record a full run of the demo case on the live URL first (the fallback); README (what it is, what was built today, how to run, libraries, live URL, video link, the tag the video was recorded at); 1-minute video recorded from the live URL; repo public; submit.

**Done when:** submitted, repo public, live URL works from a phone, video uploaded, results files downloaded (the hackathon account is deleted tonight).

---

## If behind, cut in this order

1. R4-R6 live wiring (they stay unit-tested).
2. Set F one-call-math baseline (keep the hand-checked code results).
3. Carbon explanations (show disagreements without the "likely right" note).
4. Persistent sandbox (fresh sandbox per fix).

**Never cut:** the P&ID box, the Decisions API in some role, set E with keys committed first, the server re-check of every fix, folder/file upload.

## Demo script (3 minutes)

| Time | Show |
|---|---|
| 0:00-0:20 | The real BHEL contradiction: same pumps, 1W+1S on one page, 2W on another |
| 0:20-1:50 | Judge types a change. Progress, pages found, pump boxed on the P&ID, calc sheet with flags and their sources, verdict |
| 1:50-2:30 | Agent proposes a third pump, server re-check proves it. A later change that removes the third pump is BLOCKed by the register |
| 2:30-3:00 | Results table (set E first) and where it still fails |

Fallback: the recorded run from phase 6, labelled with its time.
