# Phase 4 spec — Agent and register

Owner docs: `PHASES.md` (phase 4; cut-line 15:20), `ARCHITECTURE.md` §1 steps 10-12, §3 (Managed Agent), §5 (plant agent fields, register), §8 (the agent cannot change rules or register), `RULES.md` (Proven), `EVAL.md` §1 (runs start now), §3 (baselines), §4 (Fix outcome, Clash caught), `CLAUDE.md` ("the agent never decides"). Builds on the code as of `93c9ac7` (phase 3). Time: 14:45-15:45. **Target prize: Best use of Gemini Managed Agents.**

## Goal

1. **Measurement runs start in the background** (first 15 minutes), so phase 5 only collects.
2. After a BLOCK, the engineer clicks **Find a fix**. A Gemini **Managed Agent** (Antigravity, model Neon) works in **its own persistent sandbox for this plant**, which already holds a read-only copy of the rule engine. It edits candidate fixes and **runs the real rules on each**, at most 8 tries, then proposes one fix or refuses with reasons.
3. **The server re-runs everything itself** (rules + register) on the proposed fix. "Proven" appears only if the server agrees. The agent's own numbers are shown as the agent's claims, never as results.
4. The engineer **approves** → the register in Firestore records it. A later change that undoes it is **BLOCKed by the register check** before any fix is asked for.

---

## Part 1 — Measurement runs (first 15 minutes; Bhargavi starts them)

**Gate:** every key is committed (E at 12:47, A 12:44 + A2 fix 12:48, B 14:03). The runner refuses to start if any `eval/keys/*.json` is uncommitted or modified (`git status --porcelain eval/keys` empty).

`scripts/eval_run.py --plant <id> --sets E,A,B [--repeat-e 3]` (Bhargavi runs; needs the key; runs on her laptop with the gcp store, in the background while the agent is built):
- **Interlock:** each E and A change through `check_change` exactly as the product (same plant, same settings, frozen threshold 0.25); E three times each, A once. B through the drawing step as `score_b.py` (already run once; rerun once more for the record).
- **Keyword baseline** (`eval/baselines/keyword.py`, no model): pages containing the change's item name **as typed** (spaces/case ignored, nothing else).
- **One-call baseline** (`eval/baselines/one_call.py`): one Argon call (thinking `low`, structured output) with the plant's pages block (same order as the long read, so the cache applies) and the change: "list every page about this item, its values with page and quote, and whether the change is safe (BLOCK / REVIEW / no conflicts found)". E three times each, A once.
- Every run writes raw JSON to `eval/results/<set>_<id>_<system>_<run>.json` with `started_at`, `seconds`, the full output. Commit them as they finish. **No scoring in this phase** (phase 5 scores; `EVAL.md` §5 only).
- Rate care: one change at a time; a 429 waits 10 s and retries once; a failed run is written as failed, never skipped.
- Pages are compared by basename later (`bhel/Part3.pdf` = `Part3.pdf`).

## Part 2 — The agent

### 2.1 What the agent may change (fix levers)

The fix space is data in `app/agent/levers.yaml` (not Python), shown in the prompt, and enforced by the server re-check (a fix touching anything else is refused):

| Input | Allowed values |
|---|---|
| `line_nb` | standard sizes 50, 65, 80, 100, 150, 200, 250, 300 NB |
| `installed` | current installed + 1 or + 2 (add pumps) |
| `arrangement` / `standby_required` | only by adding installed pumps; never fewer standby than the documents require |
| `line_role` | never (a fact of the drawing) |
| the change's own values | never (the engineer's change is the question, not a lever) |

### 2.2 The sandbox (one per plant, persistent)

- **First fix on a plant** (`environment="remote"`): the input installs a **read-only bundle**: `app/rules/*.py` + `rules.yaml` (the exact files in this deploy; bundle hash = sha256 of their bytes) written to `/workspace/interlock_rules/` and `chmod -R a-w`. The agent confirms by running a 3-line smoke test (R1 on 210 m3/h, 200 NB → 1.86). The returned `environment_id` and `interaction id` are stored on the plant (`agent: {environment_id, last_interaction_id, bundle_hash}`).
- **Later fixes on the same plant**: `environment=<environment_id>`, `previous_interaction_id=<last id>`; the bundle is reinstalled only if the deploy's bundle hash changed. This is the persistence: the plant's sandbox already has the engine and the history of earlier fixes.
- **Per run**: the input carries `case.json` (the change, the after-change inputs with citations, the checked limits, the rule results that failed) and `register.json` (approved entries for this plant), written read-only into `/workspace/runs/<change_id>/`.
- Agent config: `{"type": "antigravity", "model": MODEL_NEON, "max_total_tokens": agent.max_total_tokens (100000)}`; wall clock limit `agent.timeout_s` (300); poll every 5 s. All in `app/agent/agent.yaml`.
- **Cut-line 15:20 (PHASES.md):** if the persistent sandbox fails, every fix uses a fresh `environment="remote"` with the bundle sent each time. Store a flag `agent.persistent: false` and say so in the result.

### 2.3 The task given to the agent (prompt in `app/agent/prompt.md`)

- "You are checking a fix for this change. You may only change the inputs listed in levers. For each candidate: write it to `/workspace/runs/<id>/try_<n>.json`, run `python -m interlock_rules.check try_<n>.json` (a 20-line runner included in the bundle that calls `run_rules` and the register check from `register.json` and prints the results), read the output. At most 8 tries. Prefer the smallest change (fewest inputs, smallest size step). Stop at the first candidate where no rule is flagged and no rule newly held and no register clash. If none of 8 works, refuse."
- Final answer: write `/workspace/runs/<id>/answer.json` and print it as the last thing:
```
{"outcome": "proposed" | "refused",
 "fix": [{"input": "installed", "from": "2", "to": "3", "unit": "count", "why": "..."}],
 "tries": [{"n": 1, "candidate": {...}, "flagged": ["R2"], "newly_held": [], "clashes": 0}],
 "reasons": ["..."]}
```
- **Reading the answer (no hand-parsed JSON):** first check in the installed SDK whether `interactions.create` with `agent=` accepts `response_format`; if yes, use it with schema `AGENT_ANSWER`. If not, one Hydrogen structured-output call turns the agent's final text into `AGENT_ANSWER` (role `agent_answer`, thinking low). Either way the server validates every field against `levers.yaml`; anything outside → `refused` with "agent proposed a change outside the allowed levers".

### 2.4 Server re-check (`app/agent/recheck.py`, no model) — the agent never decides

- Take the change's stored `after_values` (from the change result), overlay each fix value as `Value(source="fix", quote=<fix why>)`, rebuild inputs with `scenario.build_inputs` (same mapping as the change check), run `run_rules(live_only=True)` with the change's checked limits, run `find_clashes` against the **current** register (read fresh from Firestore), then `proven(before=change's results_after, after=new results, clashes)`.
- Result: `{"proven": bool, "reasons": [...], "results_fixed": [...], "clashes": [...]}`.
- Shown on screen as **"Proven by the server"** only if `proven` is true. The agent's tries are shown as "agent's tries (its own runs in its sandbox)". If the agent said "proposed" but the server says not proven → shown as **"Agent's fix not proven by the server"** with the reasons. This disagreement case is tested.
- A disagreement between documents (the verdict's BLOCK reason) is not something a fix can remove: the screen keeps it listed under "still to resolve by the engineer: documents disagree on …". `proven` covers rules and register only, as RULES.md defines it.

### 2.5 Approve → register (`app/register/write.py`, no model)

- `POST /changes/{id}/approve` (access code): only when the latest fix for this change is proven; runs the server re-check **again** (the register may have changed since); if still proven, writes one register entry per changed attribute (the change's values and the fix's values): `{entry_id, item, names, system, attribute, value, unit, approved_at, change_id, fix: true|false}` under `plants/{plant_id}/register/`. Returns the entries. 409 if not proven.
- `GET /plants/{id}/register` lists entries (newest first).
- The next change check overlays approved values on the as-issued inputs (already in `scenario.py`) and runs the clash check (already in `clash.py`). Example: after approving "installed 3", a change "remove the third SG Unit-1 floor wash pump" (Neon maps to `installed: 2`) → clash → **BLOCK**, "clashes with approved change <id>: installed approved 3, proposed 2".

### 2.6 API, jobs, screen

- `POST /changes/{id}/fix` → `{job_id}`; job steps: `prepare` (bundle, case) → `agent` (with elapsed seconds, polled status) → `read answer` → `server re-check`. Result stored on the change as `fix: {outcome, fix, tries, reasons, recheck, environment_id, persistent, seconds}`.
- Screen, under the verdict when it is BLOCK or REVIEW: button **Find a fix**; while running "Agent working in the plant's sandbox… 37 s"; then the agent's tries as a small table (try, candidate, what failed); the proposed fix; the server stamp (**Proven by the server** green / **Not proven** amber with reasons); button **Approve** (only when proven) → "Added to the plant's register" with entry ids. A **Register** list (item, attribute, value, approved at) under the plant line.

### 2.7 Demo cases (checked by tests with fakes, then live)

1. **Floor-wash (A1):** BLOCK (documents disagree; R2 2 < 2 + 1). Agent tries `installed 3` → R2 OK, R1 1.86 m/s OK (drawing's 200NB header), R3 still held (held before) → proven by the server. The disagreement stays listed for the engineer.
2. **Impossible change:** "SG Unit-1 floor wash water transfer pumps: run both at 400 m3/h each into the existing header." 800 m3/h: even 300 NB (largest lever) gives 3.14 m/s > the header limit → after 8 tries (or fewer, once all sizes fail) → **refused** with "no allowed line size keeps velocity within the D5-200 limit for the line's role".
3. **Clash:** approve fix 1, then "SG Unit-1 floor wash pumps: remove the third pump" → BLOCK by the register before any fix is asked.

## 3. Files

```
app/agent/
├── agent.yaml        model role, max_total_tokens, timeout_s, poll_s, persistent
├── levers.yaml       the fix space (2.1)
├── prompt.md         the agent's task (2.3)
├── bundle.py         read-only rules bundle + check runner + hash
├── run.py            create/reuse sandbox, poll, read answer (via models.py)
└── recheck.py        server re-check (no model)
app/register/write.py approve -> register entries
app/reading/models.py + agent(input, environment, previous_id) and agent_answer extraction
app/api/main.py       + /changes/{id}/fix, /changes/{id}/approve, /plants/{id}/register
web/                  fix panel, register list
scripts/eval_run.py   eval/baselines/keyword.py   eval/baselines/one_call.py
tests/test_agent_*.py tests/test_register_write.py tests/test_eval_gate.py
```
ARCHITECTURE.md §1 steps 10-12 and §5 (plant `agent` fields) updated in the same commit as the code.

## 4. Tests (no network; fake agent)

- Bundle: contains only `app/rules` files + runner; hash stable; runner prints R1 1.86 for the smoke case (run locally in the test).
- Run: first fix creates a sandbox and stores `environment_id`; second fix on the same plant reuses it with `previous_interaction_id`; bundle hash change reinstalls; persistent false → fresh sandbox each time.
- Answer: outside-lever fix → refused; malformed answer → refused "agent answer unreadable".
- Re-check: demo 1 proven; agent says proposed but server finds R1 flagged → not proven with reasons; clash after approval → not proven.
- Approve: 409 when not proven; writes entries; re-check rerun at approve time.
- Clash end-to-end with fakes: approve installed 3, then a change to installed 2 → verdict BLOCK with the clash reason.
- Eval gate: runner refuses with a modified key file.
- Agent never imported by `app/rules` or `app/verdict` (existing guard).

## 5. Build order

1. (15 min) eval gate, keyword + one-call baselines, `eval_run.py` → Bhargavi starts E, A, B in a second terminal and leaves it running.
2. `levers.yaml`, `recheck.py`, `write.py`, routes for approve/register, tests (no model) → demo 3 (clash) works with fakes.
3. `bundle.py`, `run.py`, `models.agent`, answer reading, `/fix` job, tests.
4. Screen. Deploy. Bhargavi runs demo 1, then 2, then 3 on the live URL (after a warm-up check).
5. 15:20: if the persistent sandbox is failing, switch `persistent: false`, commit with the reason.

## 6. Bhargavi does herself

1. Start `eval_run.py` (command from Claude Code) and leave it running; paste the last lines when it ends.
2. Deploy when told. Warm-up check. Run demo cases 1, 2, 3 on the live URL; paste the fix panel results (or screenshots).
3. Confirm the agent's proposed fix is engineering-sense (third pump), and the refusal reason for case 2.

## Out of scope

The agent changing rules, limits or the register; the agent reading the PDFs; fixes for disagreements between documents; scoring (phase 5); R4-R6 live.

## Done when (`PHASES.md` phase 4)

- [ ] Eval runs for E (×3), A, B started before the agent work, keys untouched; raw outputs committing to `eval/results/`.
- [ ] Floor-wash change: the agent proposes a fix in the plant's sandbox and the server re-check marks it **proven**; the screen shows the agent's tries and the server stamp separately.
- [ ] The impossible change is **refused** with a reason.
- [ ] After approval, a clashing change is **BLOCKed** by the register check.
- [ ] Second fix on the same plant reused the same `environment_id` (or the 15:20 switch recorded with its reason).
- [ ] `pytest -q` green; `done (phase-4-agent)`, tag, deployed.

---

## Amendments (Bhargavi's review, 14:35; these override the text above)

Found by re-reading this spec against the code at `f99d754`.

**M1 Bundle imports.** `app/rules/*.py` import `app.rules.*` and `yaml`. The bundle keeps the package path: `/workspace/interlock/app/__init__.py` + `/workspace/interlock/app/rules/*` (read-only), runner run as `cd /workspace/interlock && python -m app.rules.check <try.json>`. The runner uses `rules.json` (the bundle converts `rules.yaml` to JSON at build time; `load_rules` accepts a `.json` path) so the sandbox needs no `pyyaml`. The smoke test in 2.2 proves it before any fix. No key, no `.env`, nothing outside `app/rules` goes into the sandbox.

**M2 The sandbox checks rules only; the register is server-only.** `clash.py` depends on `app.reading`, so it is not bundled. The agent receives `register.json` for awareness ("never undo an approved entry"), but the register check runs **only in the server re-check**. §2.3's runner text changes accordingly; ARCHITECTURE §8's "the agent cannot change the rules or the register" stays true.

**M3 What the agent edits.** `case.json` carries the after-change **rule inputs per rule** (`inputs_by_rule`, every Value/Disputed serialised with its citation) and the checked limits. A lever maps 1:1 to a rule input (`line_nb` → R1; `installed` → R2). The runner applies the candidate's overrides to those inputs and calls `run_rules`. `model.py` gains `to_dict`/`from_dict` for `Value`, `Disputed`, `DocLimit` (round-trip tested).

**M4 Server re-check rebuilds, it does not reuse.** The change result does not store `after_values` (they are objects). `recheck.py` rebuilds the scenario from the stored checked values, drawing readings, shared-discharge values, limits and the understanding's changes, with the **current** register (item- and unit-tag-matched, per the pre-phase-4 fix 7a), then overlays the fix values (`source "fix"`), then rules + clash + `proven`. Test: rebuild without a fix reproduces the stored `results_after` exactly.

**M5 Register entry fields.** Each entry also stores `unit_tag`, so overlay and clash match on item **and** unit tag (fixes 7a/7b).

**M6 The engineer stays in control of the disagreement.** Approve is allowed only when the fix is proven **and** the engineer ticks "I have resolved the document disagreement: <attribute> (<pages>)" for every disagreement listed. The tick and its text are stored on each register entry (`resolved_disagreements`). Without the tick: 409 "documents disagree; resolve before approving".

**M7 Keyword baseline input.** EVAL §3 says "the item name as typed". Free-text changes have no fixed item field, so the baseline searches for Neon's `item` string exactly as Neon returned it, with no names expansion, no long read, no same-item check. Disclose this in EVAL §3 in the same commit. It measures what the long read, names and same-item check add.

**M8 Tries are the agent's report.** The server cannot see the sandbox's runs. Screen label: "agent's tries (reported by the agent from its sandbox)". The agent writes each try and runner output under `/workspace/runs/<id>/`; the second fix on the plant asks it to list that folder, which shows the persistence on screen.

**M9 Demo timing.** An agent run can take 1-3 minutes. Record one full run of demo cases 1-3 on the live URL as soon as they pass (it is also phase 6's fallback). Live, start "Find a fix" and talk over the progress.

**M10 Eval runs and the live demo share one key.** `eval_run.py` runs one change at a time with a 5 s pause, and stops (writing what it has) by 16:00 so the demo and the video never queue behind it.
