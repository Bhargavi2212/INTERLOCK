# Phase 4 — build plan (for approval)

Implements `docs/specs/PHASE_4.md` **with its Amendments M1-M10** (they override). **Approved 21 Nov 14:41**: D1 (a) then (b), D2, D3, D4, and two changes:
1. **Eval plant ≠ demo plant.** All eval runs use plant "BHEL files" `27d049ccd64f`, re-ingested after the pre-phase-4 deploy; `eval_run.py` refuses if that plant's register is not empty and writes `plant_id` into every result file. Demos stay on `9eeb30bca0d5`. Noted in `EVAL.md` §1.
2. **Sandbox renewal, not remount.** A changed bundle hash creates a **new** sandbox (stored; the fix result says "sandbox renewed: rules changed"). The smoke test also attempts a write under `/workspace/interlock/app/rules/` and must see it fail; otherwise stop with "bundle not read-only". Every step ends in a commit staging files **by name**, with `pytest -q` green. Claude Code never runs anything that needs the Gemini key.

Clock: 14:40 now. Phase 14:45-15:45; **cut-line 15:20** (persistent sandbox → fresh per fix). Eval runs stop by 16:00 (M10).

Checked in the installed SDK (not guessed):
- Agent `interactions.create` accepts `agent`, `agent_config`, `environment`, `previous_interaction_id`, `system_instruction`, **`response_format`** (+ `response_mime_type`), `background`.
- `environment.sources`: `[{type: "inline", content, encoding: "base64", target}]` mounts files into the sandbox.

## 0. Open decisions (need Bhargavi before step P3)

| # | Decision | Recommendation |
|---|---|---|
| D1 | A1's R1 after the pre-phase-4 fix (1): if the re-run shows R1 held (Argon's 200NB nearest another pump label), (a) tune the drawing prompt to "the size label nearest to this item's own pump discharge" on set A, recorded; or (b) keep R1 held and demo 2 becomes a test-only case | (a), then re-run A1; if still held, (b) |
| D2 | Bundle into the sandbox by `environment.sources` inline mounts (files at `/workspace/interlock/...`) instead of the agent writing them from the prompt | yes |
| D3 | `installed` lever base = register value if approved, else documents; disputed installed → no lever → refused with that reason | yes |
| D4 | Eval order: Interlock E×3, A, B first, then the one-call baseline (cache stays warm; fewer 429s) | yes |

## 1. Step P1 — measurement runs (14:45-15:00) → Bhargavi starts them

### Commit P1 `phase 4 P1: eval runner, keyword and one-call baselines`
- `scripts/eval_run.py --plant <id> --sets E,A,B [--repeat-e 3] [--systems interlock,keyword,one_call] [--stop-at 16:00]`:
  - **Gate:** `git status --porcelain eval/keys` must be empty, else exit "keys modified or uncommitted".
  - Order (D4): Interlock E (3 runs each), A (once), B (`score_b` logic, once); keyword E, A; one-call E (3 each), A.
  - One change at a time, 5 s pause (M10); a 429/5xx waits 10 s, retries once; a failure is written as failed.
  - Writes `eval/results/<set>_<id>_<system>_<run>.json` with `started_at`, `seconds`, full output; prints one line per run; stops cleanly at `--stop-at`.
  - Never reads any key field into a model call except the change text (E/A `change`, B `item_query`).
- `eval/baselines/keyword.py` (M7): pages containing Neon's `item` string exactly (spaces/case ignored), no names, no long read, no same-item.
- `eval/baselines/one_call.py`: one Argon call, thinking low, structured output: pages block (same bytes as the long read, cache applies) + the change: pages about the item, values with page and quote, verdict BLOCK / REVIEW / no conflicts found.
- `EVAL.md` §3: keyword baseline disclosure (M7).
- Tests: gate refuses a modified key; keyword baseline is a pure function (page list from text); one-call parses its structured output (fake model); file naming.
- **Bhargavi** (second terminal, leave running): `python scripts/eval_run.py --plant 9eeb30bca0d5 --sets E,A,B --repeat-e 3 --stop-at 16:00`. I commit `eval/results/*` by name as they arrive.

## 2. Step P2 — re-check, register, approve (no model) (15:00-15:15)

### Commit P2a `phase 4: serialisable values and results; rules load from JSON`
- `model.py`: `to_dict`/`from_dict` for `Value` (box tuple), `Disputed`, `DocLimit`, **`RuleResult`** (gap 3). Round-trip tests.
- `engine.load_rules`: `.json` path read with `json`; `yaml` imported only for `.yaml`; default falls back to `rules.json` beside the module when `rules.yaml` is absent (gap 2). Test: engine runs with only a `rules.json` (no yaml import).

### Commit P2b `phase 4: server re-check (rebuild + fix overlay), levers`
- `scenario.build_scenario(..., fix_values=None)`: fix values (`source "fix"`) override after-change inputs (standby still never from a fix).
- `scenario.add_drawing_assumption(results, shared_readings, sc)`: moved out of `pipeline.py`, used by both (gap 4).
- `app/agent/levers.yaml`: `line_nb` sizes [50, 65, 80, 100, 150, 200, 250, 300] NB; `installed` +1 / +2 over the base (D3); nothing else.
- `app/agent/levers.py`: `allowed(fix, base)` → (ok, reason); outside → "agent proposed a change outside the allowed levers".
- `app/agent/recheck.py`: from the stored change result: checked values + drawing readings, shared, limits, understanding changes, drawing pages (from `pages_all`), **current** register (item + unit tag) → `build_scenario(..., fix_values)` → `run_rules` → drawing assumption → `find_clashes` → `proven(before=RuleResult.from_dict(results_after), after, clashes)` → `{proven, reasons, results_fixed, clashes}` (M4).
- Tests: rebuild without a fix reproduces stored `results_after` exactly (status, value, limit, assumptions, notes); demo 1 fix `installed 3` → proven (R3 held before and after); agent "proposed" but server finds R1 flagged → not proven; outside-lever fix refused; clash after approval → not proven.

### Commit P2c `phase 4: approve into the register; register list; clash end to end`
- `app/register/write.py`: entries per changed attribute (change values + fix values): `{entry_id, item, names, system, unit_tag (M5), attribute, value, unit, approved_at, change_id, fix, resolved_disagreements (M6)}`.
- `POST /changes/{id}/approve` body `{"resolved": ["<attribute>", ...]}`: 409 "no proven fix" unless the latest fix is proven; re-check **again** (register may have changed); 409 "documents disagree; resolve before approving" unless every listed disagreement is ticked; then write.
- `GET /plants/{id}/register` newest first. Store: `add_register_entries` (memory, gcp).
- Tests: approve 409s (not proven, unticked); writes entries with unit_tag and the tick text; clash end to end with fakes: approve installed 3 → change "remove the third pump" (`installed: 2`) → BLOCK with "clashes with approved change <id>: installed approved 3, proposed 2"; a Unit-2 change is not affected.

## 3. Step P3 — the agent (15:15-15:30; cut-line 15:20 applies)

### Commit P3 `phase 4: Managed Agent in the plant's sandbox; fix job`
- `app/agent/agent.yaml`: role neon, `max_total_tokens` 100000, `timeout_s` 300, `poll_s` 5, `persistent` true.
- `app/agent/bundle.py` (M1): files `app/__init__.py`, `app/rules/{__init__,engine,checks,units,model}.py`, `rules.json` (from `rules.yaml`), `app/rules/check.py` (runner: read try JSON = `inputs_by_rule` + limits + overrides → `run_rules` → print JSON results); sha256 bundle hash; `sources()` → inline base64 mounts at `/workspace/interlock/...` (D2). No key, no `.env`, nothing else.
- `case.json` (M3): `inputs_by_rule` serialised with citations, checked limits, failed results, levers, the change text; `register.json` for awareness only (M2). Both mounted read-only under `/workspace/runs/<change_id>/`.
- `app/agent/prompt.md` (M2, M8): levers only; write `try_<n>.json`, run `cd /workspace/interlock && python -m app.rules.check /workspace/runs/<id>/try_<n>.json`; ≤ 8 tries; smallest change first; stop at first with no flagged, no newly held; never undo a register entry; refuse if none works; on a reused sandbox first list `/workspace/runs/` (persistence shown).
- `models.agent(input, sources, environment_id, previous_id, schema)`: first fix `environment={"type": "remote", "sources": [...]}`; later fixes `environment=<id>`, `previous_interaction_id`; a changed bundle hash creates a new sandbox ("sandbox renewed: rules changed"); `response_format=AGENT_ANSWER` (fallback: one Hydrogen structured call on the final text); poll to `timeout_s`; returns answer, `environment_id`, interaction id.
- `app/agent/run.py`: smoke test on a new sandbox (R1 210 m3/h, 200 NB → 1.86, and a write under `/workspace/interlock/app/rules/` must fail, else stop "bundle not read-only"); store `plant.agent = {environment_id, last_interaction_id, bundle_hash, persistent}`; validate the answer (levers, fields) → else refused "agent answer unreadable" / "outside the allowed levers"; then `recheck`.
- `POST /changes/{id}/fix` → job steps `prepare` → `agent` (elapsed s) → `read answer` → `server re-check`; result stored on the change as `fix`.
- ARCHITECTURE.md §1 steps 10-12, §5 plant `agent` fields: same commit.
- Tests (fake agent): first fix creates and stores the sandbox; second reuses `environment_id` + `previous_interaction_id`; hash change remounts; `persistent: false` → fresh each time; outside-lever and malformed answers refused; bundle contains only the listed files, runner prints 1.86 for the smoke case (run locally in the test); agent code never imported by `app/rules` or `app/verdict`.

## 4. Step P4 — screen, deploy, live demos (15:30-15:45)

### Commit P4 `phase 4: fix panel and register on the screen`
- Under a BLOCK/REVIEW verdict: **Find a fix**; "Agent working in the plant's sandbox… N s"; "agent's tries (reported by the agent from its sandbox)" table (M8); proposed fix; server stamp **Proven by the server** / **Agent's fix not proven by the server** + reasons; "still to resolve by the engineer: documents disagree on …" with a tick box per disagreement (M6); **Approve** enabled only when proven and all ticked → entry ids. **Register** list under the plant line.
- **Deploy.** Bhargavi: warm-up check; demo 1 (A1 → Find a fix → proven → tick → Approve); demo 2 (impossible change, if D1 allows); demo 3 ("SG Unit-1 floor wash pumps: remove the third pump" → BLOCK by the register). **Record one full run as soon as all pass** (M9; phase 6 fallback).
- 15:20 cut-line: if the persistent sandbox fails, `persistent: false`, commit with the reason (PHASES.md).

## 5. Done-when (how checked)

| Check | Evidence |
|---|---|
| Eval E×3, A, B started before agent work; keys untouched | runner start line + `git status eval/keys` empty; raw files committed |
| Floor-wash: agent proposes in the plant's sandbox; server marks proven; tries and stamp shown separately | screenshot + stored `fix` |
| Impossible change refused with a reason | screenshot (or test-only per D1(b), recorded) |
| After approval, a clashing change is BLOCKed by the register | screenshot + verdict reason |
| Second fix reused the same `environment_id` (or the 15:20 switch recorded) | stored `plant.agent` + fix result |
| `pytest` green; `done (phase-4-agent)`; tag; deployed | outputs |

## 6. Risks

| Risk | Response |
|---|---|
| R1 held on A1 after fix (1) | D1 |
| Sandbox lacks Python or the mount fails | smoke test fails fast → fresh-sandbox mode or bundle in the prompt; recorded |
| Agent slow (1-3 min) | job with progress; M9 recording |
| Eval 429s collide with the demo | one change at a time, 5 s pause, stop 16:00; pause the runner during the recording |
| Behind at 15:20 | P2 (no model) is done first: demo 3 works without the agent; switch `persistent: false` |

## 7. Approve

Reply "approved" with D1-D4 (or changes). I start at P1.
