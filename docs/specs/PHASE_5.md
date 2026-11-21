# Phase 5 spec — Proof

**The Amendments section at the end overrides the text above it.**

Owner docs: `EVAL.md` (§1 rules, §2 sets and keys, §3 baselines, §4 metrics, §5 the only home of results, §6 where it fails), `PHASES.md` (phase 5), `CLAUDE.md` (measured numbers live only in EVAL.md). Builds on `42de01d`. Time: 15:50-16:15. **Every number in §5 comes from code run on today's committed raw outputs.** Nothing is typed by hand into §5 except "n/a".

## 0. Ground rules (read first)

1. **Score the runs as they are.** Set E and A runs in `eval/results/` were made before the E5 fix (`42de01d`). They are scored as measured. **No set E rerun** after a fix (that would be tuning on the test set). §6 says which fixes came after which runs.
2. **Keys before runs:** the scorer checks, for every scored result file, that its key's last commit time is earlier than the result's `started_at`, and prints the check. A failure is reported in §5's notes, never hidden.
3. **Same scoring for every system** (EVAL §1.3). Pages compared by **basename + page** (`bhel/Part3.pdf` = `Part3.pdf`). Pages a system labels "design basis" are excluded from recall and wrong pages for that system (they are cited limits, not pages about the item).
4. **No model calls in scoring.** `score_eval.py` is pure code.

## 1. `scripts/score_eval.py` (Claude Code; no key needed)

Reads `eval/keys/*.json` and `eval/results/*.json`; writes `eval/results/scores.json` and prints a markdown table. Per system (`interlock`, `one_call`, `keyword`):

| Metric | Definition (code) |
|---|---|
| Page recall | per run: key pages found / key pages. Set E: **worst of 3 per change, then mean over changes**, plus spread (min-max per change). Set A: one run, mean. |
| Wrong pages | per run: returned pages not in the key. Set E: total per change, worst of 3; report sum and per change. |
| Value accuracy | a key value is matched if the system returned a value on the **same file+page** whose number equals the key's (numbers as numbers; counts via `counts_in_text`; arrangements via `parse_arrangement`) and whose unit is compatible (`units.to_base` same quantity) or both are counts. Attribute names are not compared (systems name them differently); stated in EVAL §4. Mean over keys, worst of 3 for E. |
| Evidence | Interlock: values with `evidence_ok` / values returned. One call: the same `quote_on_page` code applied to its quotes (it had to give quotes). Keyword: n/a. |
| Verdict matches key | runs whose verdict equals `expected_verdict` / runs. **New row in §5**, added because it is in every key; reported whichever way it falls. |
| Same-item check P/R | Interlock set A only: over candidate pages (kept + rejected), positive = key page; precision and recall of "kept". |
| Drawing hits | set B from `B_all_interlock_*.json` (and `b_141730.json`): hits / 5. |
| Time | Interlock and one call: median and max `seconds` per set. |

Output also lists every **miss** (change, system, run, missing key pages, wrong pages, wrong verdict), which feeds §6.

Tests (`tests/test_score_eval.py`): basename matching; design-basis exclusion; worst-of-3; a value on the wrong page is not matched; key-before-run check flags a result older than its key.

## 2. Set F — code math vs one Gemini call doing the math

- `scripts/run_f.py` (Bhargavi runs; needs the key for the one-call part):
  - **Interlock (code):** for each `F*.json`, build the inputs from the key's `inputs` (value, unit, file, page, quote; `source: document`, `evidence_ok: true`) and the D5-200 band where given; run the rule with `run_rule`. No model.
  - **One call doing the math** (EVAL §3): one Argon call (thinking low, structured output `{value, unit, status, working}`) given the same pages' text (the F inputs' pages) and the calculation sentence from the key; "compute it".
  - Writes `eval/results/F_<id>_<system>.json`.
- Scored by `score_eval.py`: math correct = within 1% of `expected.value` (EVAL §4) and status equal; F2 compares the pump-out time (30.0 min) and status held.
- **Key check:** F keys committed 12:44, before these runs. F inputs come from the keys (that is the point of set F: the same inputs to both systems).
- **Cut first if behind** (PHASES cut order item 2): then the one-call cell is "n/a (not run)", the code result still runs (it needs no key).

## 3. Demo outcomes (fix and clash rows)

- `scripts/collect_demo.py --change <id> [--change <id> ...]` (Bhargavi runs; access code from the environment, never printed): `GET /changes/{id}` from the live URL; writes `eval/results/demo_<id>.json` with the change text, verdict, `fix` (outcome, recheck proven/reasons, environment_id) and clashes.
- §5 rows: **Fix proven / refused correctly** = demo cases whose outcome matches the spec (demo 1 proven, demo 2 refused); **Clash caught** = demo 3 BLOCKed with a register clash. These are 2-3 cases, labelled as demo cases in §5, not a test set.

## 4. By hand (optional, cut if past 16:00)

EVAL §3: Bhargavi times herself doing A1 with a PDF reader and Ctrl-F (stop when she has the pages and the verdict). One expert, one change, disclosed as the builder. If not done: the column says "n/a (not run)".

## 5. Timing (review item 9)

From the raw outputs only: Interlock cold (first check on a plant, e.g. A1 run at 99 s) and warm (median of later runs). Both go in §5 "Time per change" as "warm median / cold". No new runs needed.

## 6. `EVAL.md` §5 and §6 (Claude Code, from `scores.json` only)

- §5 table: every cell a number from `scores.json` or "n/a"; add the **"Verdict matches key"** row; a note under the table: "E and A runs made 14:55-15:3x before fix `42de01d`; scored as measured."
- §6, at least these, worded plainly:
  - Set E verdicts: one Gemini call matched the key verdict more often than Interlock (numbers from `scores.json`). Interlock's difference is checked quotes, code math with cited limits, the drawing box, and the server-proven fix, which one call does not give.
  - E5: Interlock said REVIEW in 3/3 runs (key BLOCK): a change saying "no spare" set the standby requirement to 0. Fixed after the runs (`42de01d`, test added); E5 is scored as measured.
  - The other misses printed by the scorer (pages missed, wrong pages per change, E4's wrong-page spread).
  - A3 phase 2: read 65NB from the downstream line instead of the pumps' 50NB (drawing step since added).
  - The sandbox does not support read-only mounts (already written).
  - 46 pages with no readable text are never read; the verdict label says so.
  - Low-confidence pages are kept by design (7c): count how many such pages Interlock returned on set E and how many were wrong.
  - Cold first check ~100 s; warm ~35-70 s.

## 7. Product fixes in this phase (only if §1-§6 are done; each with a test; never rerun set E)

In this order, stop at 16:10:
1. **"Incomplete" verdict (7d):** values step failed or returned nothing → verdict label "Incomplete: values could not be read", never a plain REVIEW. RULES.md Verdict updated.
2. **Count next to its marker (7e).**
3. **Role-based stricter band (10).**
4. Guard tests (item 6): **cut** unless time remains; listed in §6 as "guard tests check ids, limits and case counts; they do not parse each case's inputs".

## 8. Bhargavi does herself

1. Run `python scripts/run_f.py --plant 27d049ccd64f` (eval plant) and `python scripts/collect_demo.py --change <demo 1> --change <demo 2> --change <demo 3>`; paste the last lines.
2. Optional: the timed by-hand A1.
3. Read the §6 lines and correct anything that overstates or understates.

## Done when (`PHASES.md` phase 5)

- [ ] `score_eval.py` and its tests committed; `scores.json` committed; the key-before-run check passes (or its failure is reported).
- [ ] Every §5 cell holds a number from `scores.json` or "n/a"; the "Verdict matches key" row is present.
- [ ] §6 holds every miss the scorer printed, the E5 note, and the items in §6 above.
- [ ] Set F scored (code at least); demo outcomes collected.
- [ ] `pytest -q` green; `done (phase-5-proof)`, tag pushed. (No deploy needed unless §7 fixes went in.)


---

## Amendments (approved 21 Nov ~15:55; these override the text above)

**G1 Eval plant without the drawing step.** All 18 Interlock E/A runs say "no drawing page among the pages found", and B on `27d049ccd64f` scored 1/5 (5/5 on the demo plant): the eval plant was never re-ingested after phase 3 (its `pages_all` had no `is_drawing`). Bhargavi re-ingests it, then reruns `eval_run.py --sets E,A,B --repeat-e 3 --systems interlock --stop-at 16:20` **from a git worktree at `fc7dadb`** (the original runs' code: no set E tuning), with the project `.venv`; outputs copied to `eval/results/rerun/`. **Both are scored. §5 reports the rerun; §6 explains the first runs ("drawing step inactive: plant not re-ingested after the phase 3 fix") and keeps their numbers visible.**

**G2 Set F limits.** `run_f.py` turns each F key's `velocity_band` into a `DocLimit` with `applies_to` from the key (else from the quote's role words; never silently the 3.0 m/s default). F1's 200NB line is a header (2.1-2.4 m/s) on the drawing; with no role in the key the band applies as pump discharge (2.1-2.5); the result (1.86 m/s OK) is unchanged and §6 says so.

**G3 Generous value matching.** EVAL §4 states that value matching is generous to the one-call baseline (its strings like "Three (2W+1S)" contain several numbers, any of which can match).

**1 Design-basis pages** count toward recall when the key lists them (A1 lists Part5 p.200); they never count as wrong pages.

**2 Interlock values** counted for value accuracy: `evidence_ok` only (the values it uses). One-call values: all returned; the Evidence row applies the same `quote_on_page` code to them. Stated in EVAL §4.

**3 Units without a quantity** (e.g. "545 m" pipe run) are compatible when equal after normalising; ranges ("2.1-2.5") are compared as their numbers.

**4 Cold / warm.** Cold = the first run on a plant by `started_at` (eval plant: E1 run 1; demo plant: 102.1 s, already in §6). Warm = median of the rest. The cache showed no hits (`cached` 0) in the eval runs; stated.

**5 Same-item row** recomputed from the eval A runs at the frozen 0.25 by the scorer; the hand-entered row from phase 2 is replaced.

**6 Demo 2** was not run live (D1 (b)): the fix row is demo 1 (live) + demo 2 (tests only), labelled so.

**7 Demo 1's proven fix** was overwritten on the change by the second "Find a fix"; `collect_demo` reads the fix **job** records and the register (approval writes entries only after a server re-check). Product follow-up: keep every fix attempt.

**8 `collect_demo`** reads Firestore with ADC (no access code, no Gemini key); Claude Code runs it.

**9 E5 wording:** "set standby_required to 'no'/'false', which R2 could not read, so R2 was held and the verdict REVIEW" (not 0).

**10 Unreadable pages:** "cannot be searched or quoted" (not "never read").

**11 Note under §5:** runs made 14:46-15:25 by Anaconda's Python (conda base), not the project `.venv`; the rerun used `.venv`.
