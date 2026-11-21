# Phase 1 — build plan (for approval)

Implements `docs/specs/PHASE_1.md` plus the 20 review fixes and Bhargavi's changes (a), (b), (c) of 21 Nov. **Approved 21 Nov** with four changes, applied in the docs and the spec's Amendments: (1) absolute marker only `(a)`, a separate `a` token, or bara / kpaa / kpa(a) / psia; plain kPa and MPa are gauge with the assumption; (2) SG 1.0 only when a water phrase matches and no solids phrase does ("sludge water" → held); (3) docs-first OK; (4) order C3, C4, C8, C5, C6, C7. Every step ends in a commit; `pytest -q` passes before each commit.

Time box: phase 1 is 12:10-12:50 and this plan starts about 12:20. The spec's build order decides what waits if time runs short (§6).

---

## 0. Decisions this plan applies

| # | Decision | Source |
|---|---|---|
| D1 | Phase 0 closes: `/health` live returned `{"status":"ok","version":"54c95db"}` (checked 11:59), `check_models` printed 6 of 6 answered. Set E stays open, due before phase 2 runs anything | (a) |
| D2 | `solids_services` and `water_services` lists in `rules.yaml`, both **CONFIRM**. Matched case-insensitively as **whole phrases**: a list phrase matches when it appears in the service text bounded by word boundaries (`\bwaste water\b`), never as a bare substring (`ash` does not match `wash`). Solids checked first | (b) |
| D3 | New R1 input `line_role`. A document band applies when `line_role` matches "pump discharge", **or is unstated** (assumption: "line assumed to be pump discharge"). Default limit only when the role is stated as something else, or no band covers the size | (c) |
| D4 | Values from the change text or an agent fix carry `source: "change"` / `"fix"`; `quote` = that text, `file`/`page` empty; they skip the evidence check. Document values keep `source: "document"` | fix 4 |
| D5 | Doc decisions are committed **first, in one docs commit** (step 2), before code. Code commits then implement them and update only README/PHASES. *(The spec says "same commit as its code"; docs-first is simpler and keeps every commit's tests green. Say no and I fold each doc change into its code commit instead.)* | plan |

**D2 consequence to confirm:** with `water_services: [water, ...]`, "floor wash water" matches `water` (SG 1.0) and "waste water" matches solids first. That is the intended order; say if "water" should not be a catch-all.

---

## 1. Step 1 — Close phase 0 (commit C1, ~3 min)

1. Re-check live `/health` (curl) right before committing; if it fails, phase 0 stays open with open items deploy, check_models, set E (per (a)).
2. `docs/PHASES.md` phase 0: `Status: done (phase-0-setup) — open item: set E keys (≥3), due before phase 2 runs anything.`
3. `docs/PHASES.md` phase 2 **Done when**, new first line: "Set E keys (≥3) committed before any change is run on the plant (carried from phase 0)."
4. Commit C1 `phase 0: done, set E carried to before phase 2`; `git tag phase-0-setup`; `git push origin main --tags`.

## 2. Step 2 — Docs commit (commit C2, ~8 min)

All edits made by a script that asserts each target text matches exactly once. One commit: `docs: phase 1 review fixes and decisions (a)-(c)`.

### `docs/RULES.md`
| Where | Change | Fix |
|---|---|---|
| Limit sources, item 2 | "...used only when no document limit is found **for that rule and that case**" | 8 |
| Every result carries | add `unit`, `notes` (information only; never changes status); inputs carry `source`, `file`, `page`, `quote`, `unit` | spec #3, 4 |
| New short section "Inputs" | sources document / change / fix (D4); text and yes/no inputs (`service`, `line_role`, `schedule`, `arrangement`, `volume_is_total`) may have an empty unit; a number with an empty unit is held | 4, 13 |
| Verdict | "documents that disagree about a changed value" — the caller passes only those | 15 |
| R1 Limits | replace the low-velocity bullet: solids service (whole-phrase match, D2) and v < band low → **flagged**; not solids → note "below the documents' lower value, information only"; service unstated → note gives both facts (below lower value X; solids check not run, service not stated). **Low side never makes the result held** | spec #1, 10 |
| R1 Limits | document bands apply to pump discharge lines; `line_role` unstated → band applied with assumption; role stated otherwise or no band covers the size → default | 11, D3 |
| R2 | default 1 always, with assumption "continuous duty assumed"; `arrangement` NW+MS supplies standby (and working only if `working` is missing); a conflict between them is a disagreement passed by the caller | 5, 6, 7 |
| R3 Held if | add "Q_in ≤ 0 or Q_out ≤ 0 → held, naming the input" | 14 |
| R5 | SG 1.0 only for services matching `water_services` (D2) | 9 |
| Units table | add: Pressure `bar(a)`/`bara`, `kPa(a)`, `psia` (convert, then −1.013 → bar(g)); Diameter `mm` ÷1000 m; Velocity `m/s` x1; Count row text becomes "`NW+MS` or `NW` for any N, M (e.g. 1W+2S, 3W); anything else unknown" | spec #2, 3, 5, 12 |
| Confirmed table | add rows "R1 solids-bearing services" and "R5 water services (SG 1.0)" | spec #4, D2 |

### `docs/specs/PHASE_1.md`
- §1 `Value`: add `source: str = "document"`. `DocLimit`: add `applies_to: str` ("pump discharge") and `evidence_ok: bool = True`; engine ignores a DocLimit with `evidence_ok=False`.
- §2 R1 inputs: add `line_role` (optional).
- §3 R1: D3 rule; low-side note text per fix 10. R2: fixes 5-7. R3: fix 14. R5: `water_services` whole-phrase (D2), not `service == "water"`.
- §4 units: diameter mm, velocity m/s, `NW+MS` pattern; empty unit only for the named text inputs.
- §6 `rules.yaml` example completed: flow aliases, volume, concentration, density, strength, `nb_to_m`, `mm_to_m`, velocity, absolute markers, `water_services`, `m3/d: 0.041666666666667`.
- §7 test 8: allowed literals add `4` and `100`.
- EVAL B example: `"page": <page where drawing D3-146 appears>` (fix 17).

### `docs/ARCHITECTURE.md`
- §5 value record: `{item, attribute, value, unit, source, file, page, quote, evidence_ok}`.
- §2 tree `scripts/`: add `find_pages.py`, `label_positions.py`.

### `docs/EVAL.md` §2
- Key formats for sets B and F (spec doc update #6), B page note (fix 17). Set A uses the change format with `"author": "Bhargavi"`.

### `CLAUDE.md`
- Hard rule: "Every value read from a document carries `file`, `page`, `quote` and `unit`…" (fix 16).

### `docs/PHASES.md`
- Phase 1: `Status: in progress`; "Detailed spec: `docs/specs/PHASE_1.md`"; Build adds `proven()`, `app/verdict/`, `scripts/find_pages.py`, `scripts/label_positions.py` (fix 18).

This plan file is committed in C2 as well.

## 3. Step 3 — Code, in the spec's build order

### C3 `phase 1: data model, units, rules.yaml` (~8 min)
- `requirements.txt` + `pymupdf==<installed>`; README Libraries row "pymupdf — PDF text, page images, text positions".
- `app/rules/model.py`: `Value`, `Disputed`, `DocLimit`, `RuleResult` (frozen dataclasses except RuleResult; `to_dict()` for JSON).
- `app/rules/rules.yaml`: spec §6 completed (C2 version), all `confirm: true`.
- `app/rules/units.py`:
  - `normalise(unit)`: lower-case; strip spaces and dots; `³→3`, `²→2`; `hr→h`; detect absolute marker (`(a)`, trailing `a` on bar/kpa/psi) and gauge marker (`(g)`, `g`).
  - `to_base(quantity, value, unit) -> (float, list[str])`, `UnknownUnit`. Factors read from `rules.yaml` only. Quantities: flow, pressure, head, nb, diameter, volume, concentration, strength, density, velocity, count.
  - `parse_arrangement("2W+1S") -> {"working": 2, "standby": 1}`; regex `^(\d+)\s*w(?:\s*\+\s*(\d+)\s*s)?$` on the normalised text; else UnknownUnit.
  - `matches_phrase(text, phrases) -> str | None` (D2), used for solids, water, line role.
- `tests/rules/test_units.py`: one case per Units table row, superscripts/spacing, unknown → UnknownUnit, `%` without w/w|w/v → UnknownUnit, absolute subtracts 1.013, arrangement pattern (`1W+2S`, `3W`, `2 W + 1 S`; `two working` → unknown), whole-phrase match (`ash` ∉ `floor wash water`; `waste water` ∈ `MRS waste water`).

### C4 `phase 1: engine and R1-R3 (live rules)` (~10 min)
- `app/rules/engine.py`: `load_rules()` (cached), `run_rule()`, `run_rules(live_only=True)`. Input gate before any check: `None` / `evidence_ok=False` (document source only) / unknown unit / number with empty unit → held naming the input; `Disputed` → held listing file, page, value of each.
- `app/rules/checks.py`: `r1_velocity`, `r2_standby`, `r3_sump` as RULES.md + D3 + fixes 5-7, 10, 14. Every limit from `rules.yaml` or a `DocLimit`; `math.isclose(rel_tol)` at the limit; no rounding except in messages.
- `tests/rules/conftest.py`: `v(value, unit, source="document")` → Value with test file/page/quote; `bhel_bands()` → the two D5-200 DocLimits (applies_to "pump discharge").
- `tests/rules/test_r1_velocity.py` (7 RULES cases + extras: line_role suction → default 3.0; role unstated → band + assumption; solids below low → flagged; unstated service → both-facts note; no band covers 175 NB → default; DocLimit evidence_ok False → ignored), `test_r2_standby.py` (3 + arrangement, default assumption), `test_r3_sump.py` (5 + q_in ≤ 0 held), `test_held.py` (missing, evidence_ok False, Disputed, unknown unit, number with empty unit; change-source value with no file/page is accepted).

### C5 `phase 1: verdict and proven` (~5 min)
- `app/verdict/verdict.py`: `verdict()` and `proven()` per spec §5.
- `tests/rules/test_verdict.py`: BLOCK by flagged / disagreement / clash; REVIEW by held; label contains N; verdict ∈ {BLOCK, REVIEW, no conflicts found}; "PASS" absent from every output (JSON-dumped); proven allows pre-existing held, refuses new held, refuses clash, ignores notes. Plus the demo case end to end with rule results: change (2 pumps, 100 NB, installed 2) → BLOCK; fix (200 NB, installed 3, sump still held) → proven.

### C6 `phase 1: R4-R6 (built, not live)` (~6 min)
- `checks.py`: `r4_relief`, `r5_design_pressure`, `r6_dose`; `live: false` in yaml.
- Tests: R4 4 cases, R5 3 cases + head in m with water service (SG 1.0 assumption) + head with other service and no SG → held, R6 3 cases + `%` unmarked → held + w/w no density → held.

### C7 `phase 1: guard tests` (~6 min)
- `tests/rules/test_rules_match_doc.py`:
  - count guard: per `## Rn`, number of "Test cases" bullets in RULES.md == number of parametrized RULES cases for Rn (each test file exposes `RULES_CASES`).
  - rule ids in RULES.md headings == `rules.yaml` ids.
  - each default == "Confirmed value" cell if filled, else "Default above" cell (numbers parsed from the cell; list rows compared as sets).
  - every `x<num>` / `÷<num>` factor in the Units table == the yaml factor (÷N vs 1/N within 1e-9); schedule ID table == yaml.
- `tests/rules/test_no_model_calls.py`: AST-scan imports in `app/rules/`, `app/verdict/`; banned `google`, `genai`, `httpx`, `requests`, `urllib`, `socket`, `app.store`.
- `tests/rules/test_no_hardcoded_limits.py`: AST numeric constants in `checks.py`, `units.py` ⊆ {0, 1, 2, 4, 60, 100, 1000, 3600}.

### C8 `phase 1: key-writing scripts` (~5 min; start as soon as C5 is green)
- `scripts/find_pages.py "name" ["alias" ...] [--dir data/bhel]`: every page whose text contains any name, case-insensitive, spaces ignored; prints `file | page | line`. Proposals only.
- `scripts/label_positions.py <pdf> <page> "<label text>"`: text-layer boxes of the phrase on that page, normalised 0-1 (`x0, y0, x1, y1`), and the box centre. Prints "not found" if absent.
- Smoke-tested on `data/bhel/` once the PDFs are there; not part of pytest (no PDFs in git).

### C9 `phase 1: confirmed values` (when Bhargavi answers)
- RULES.md confirmed table filled (value + reason); `rules.yaml` values updated and `confirm: false`; yaml ↔ doc test proves they match.

### C10 `phase 1: done` + tag `phase-1-rules` + push
- Only when every done-when line passes (§5).

## 4. Bhargavi, in parallel

| # | Task | Needs |
|---|---|---|
| B0 | Copy `Part1.pdf`-`Part5.pdf` into `D:\Hackathon\Interlock\data\bhel\` (git-ignored) | **now**, blocks the scripts and every key |
| B1 | CONFIRM answers: R1 3.0 m/s; R1 solids list; R2 1; R3 6/h; R4 0.90; R5 1.10 / 1.0 bar; R5 water services list | any time; I record them (C9) |
| B2 | Set A keys `A1-A3` with `find_pages.py` | C8 + B0 |
| B3 | Set B keys `B1-B5` with `label_positions.py` (find the page of drawing D3-146 first) | C8 + B0 |
| B4 | Set F keys `F1-F3`, worked by hand | B0 |
| B5 | Set E keys (carried from phase 0) | before phase 2 runs anything |

Keys: drop the files in `eval/keys/` and tell me; I commit them unread-by-any-system, or commit them yourself.

## 5. Done-when check (how I verify)

| Check | Evidence |
|---|---|
| `pytest -q` green: every RULES case, count guard, yaml ↔ doc, units, held, verdict/proven, no-model-calls, no-literals | pytest output with counts |
| Doc updates made | C2 diff summary |
| CONFIRM values recorded, `confirm: false` everywhere | RULES table + `grep "confirm: true" rules.yaml` empty |
| A1-A3, B1-B5, F1-F3 committed before phase 2 | `git log -- eval/keys` with times |
| Status `done (phase-1-rules)`, tag pushed | `git ls-remote --tags origin` |

Any failed line is reported as failed; the phase is not marked done.

## 6. If time runs short (spec order)

1. C3-C5 (live rules + verdict) are the core: never skipped.
2. C8 scripts move ahead of C6/C7 if the keys are blocked on them.
3. C6 (R4-R6) and C7 (guards) finish at the start of phase 2 if needed, recorded in the commit message and as a phase 1 open item.

## 7. Approve

Reply "approved" (optionally: "no docs-first" for D5, or a different D2 reading). I start at step 1.
