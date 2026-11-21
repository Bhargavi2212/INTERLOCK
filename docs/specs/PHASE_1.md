# Phase 1 spec — Rule engine

Owner docs: `RULES.md` (every formula, limit, unit factor, test case), `PHASES.md` (phase 1), `ARCHITECTURE.md` §2 (`app/rules/`, `app/verdict/`), `EVAL.md` §2 (keys A, B, F). Time: 12:10-12:50.

## Goal

A rule engine that is pure code: same inputs, same outputs, every run. It takes values that carry their evidence, runs R1-R6, and returns OK / flagged / held with the limit's source. A verdict function and a "proven" function sit on top. Phase 2 plugs Argon's values into it without changing it.

**No model calls, no network, no Firestore or Cloud Storage in this phase.**

## Files Claude Code creates

```
app/rules/
├── __init__.py        exports run_rules, run_rule, load_rules
├── rules.yaml         every limit, default and unit factor (mirrors RULES.md)
├── model.py           Value, Disputed, DocLimit, RuleResult (dataclasses)
├── units.py           parse units to SI-ish base units; unknown -> held
├── engine.py          loads rules.yaml once, dispatches R1-R6
└── checks.py          one function per rule; reads limits only from rules.yaml / DocLimit
app/verdict/
├── __init__.py
└── verdict.py         verdict() and proven()
tests/rules/
├── conftest.py        helper v(...) building a Value with a test page and quote
├── test_r1_velocity.py ... test_r6_dose.py   one file per rule
├── test_units.py
├── test_verdict.py
├── test_rules_match_doc.py   rules.yaml <-> RULES.md
└── test_no_model_calls.py    app/rules and app/verdict import nothing networked
scripts/
├── find_pages.py      text search over data/bhel/*.pdf, prints file, page, line (helps write keys A)
└── label_positions.py text-layer positions of a phrase on one page, normalised 0-1 (keys B)
```

`requirements.txt` gains `pymupdf` (pinned) for the two scripts and for phase 2 ingest; add it to README "Libraries".

## 1. Data model (`model.py`)

```python
@dataclass(frozen=True)
class Value:            # one value read from a document
    value: float | int | str      # number, or text such as "1W+1S", "water"
    unit: str                     # as printed: "m3/h", "NB", "kg/cm2(g)", "count", "% w/v", ""
    file: str                     # e.g. "Part4.pdf"
    page: int                     # 1-based within the file
    quote: str                    # exact sentence from the page
    evidence_ok: bool = True      # set by the phase 2 evidence check

@dataclass(frozen=True)
class Disputed:          # documents disagree about this input
    values: tuple[Value, ...]

@dataclass(frozen=True)
class DocLimit:          # a design-basis limit stated in the plant's documents
    rule_id: str                  # "R1"
    name: str                     # "velocity_band"
    low: float | None
    high: float | None
    unit: str
    applies_from_nb: int | None   # R1 bands: 50..150, 200..None
    applies_to_nb: int | None
    file: str; page: int; quote: str

@dataclass
class RuleResult:
    rule_id: str
    status: str                   # "OK" | "flagged" | "held"
    value: float | None           # computed number in the rule's unit
    unit: str
    limit: float | None
    limit_source: str             # "Part5.pdf p.200: '<quote>'" or "default (RULES.md, confirmed)"
    formula: str
    inputs: dict[str, Value | Disputed | None]
    message: str
    assumptions: list[str]
    notes: list[str]              # information only; never changes status
```

Rules for inputs, enforced in `engine.py` before any check runs:
- An input that is `None` (missing), has `evidence_ok=False`, or has an unknown unit → treated as missing → that rule is **held** and the message names the input.
- An input that is `Disputed` → **held**, message lists every file and page and value. (The verdict's "documents disagree" comes from the caller, see §5; the engine does not decide it.)
- The engine never fills a missing input with a guess. Defaults exist only for **limits** listed in `rules.yaml`, never for measured values (no default density, no default SG except the water rule below).

## 2. Entry points (`engine.py`)

```python
load_rules(path=None) -> dict          # parsed rules.yaml, cached
run_rule(rule_id, inputs: dict, doc_limits: list[DocLimit] = ()) -> RuleResult
run_rules(inputs_by_rule: dict[str, dict], doc_limits=(), live_only=True) -> list[RuleResult]
```

`live_only=True` runs only rules with `live: true` in `rules.yaml` (R1, R2, R3). R4-R6 have `live: false` and run in tests and when called by id.

Input names per rule (phase 2 must produce exactly these):

| Rule | Inputs |
|---|---|
| R1 | `flow_total` **or** (`flow_per_pump` + `pumps_into_line`); `line_nb` and/or `line_id` and/or `schedule`; `service` (optional) |
| R2 | `installed`, `working`, `standby_required` (optional; text like "1W+1S" also accepted in `arrangement`) |
| R3 | `volume`, `q_out`, `q_in` (optional), `volume_is_total` (optional bool) |
| R4 | `operating`, `set`, `design` |
| R5 | `design`; either (`max_suction` + `shutoff_head`, plus `sg` or `service`) or `operating` |
| R6 | `dose`, `flow`, `strength`, `density` (w/w only), `pump_min`, `pump_max` |

## 3. Each rule (behaviour exactly as `RULES.md`; points below settle what RULES.md leaves open)

**R1 pipe velocity**
- Q = `flow_total`, or `flow_per_pump x pumps_into_line`. If `pumps_into_line > 1`, add assumption "upper bound for parallel pumps on a shared header".
- If only `flow_per_pump` is given and `pumps_into_line` is missing → **held** ("documents do not show how many pumps run into this line").
- D: `line_id` if stated; else `line_nb` + `schedule` from the ID table in `rules.yaml`; else `line_nb / 1000` with the assumption "nominal bore used as internal diameter" (and the over/under-statement sentence from RULES.md).
- Limit: the `DocLimit` for R1 whose NB range contains `line_nb` → its `high` is the check, `limit_source` cites file, page, quote. No band matches (or `line_nb` unknown) → default `r1.max_velocity` from `rules.yaml`, `limit_source` = "default".
- Low side: if `service` is solids-bearing (list in `rules.yaml`) and v < band low → **flagged**. If v < band low and service is not solids-bearing → note "below the documents' lower value, information only". If v < band low and service is unstated → note "low-velocity check not run: service type not stated". **Low side never makes the result held.** (This settles the conflict between "unstated → low check held" and the test case "210 m3/h, 200 NB → OK"; Claude Code updates the RULES.md R1 wording to this in the same commit.)

**R2 standby**: `standby_required` from the documents (`arrangement` "1W+1S" → working 1, standby 1) else default from `rules.yaml` with limit_source "default". Flagged message: "installed N < working W + standby S".

**R3 sump cycle**: as RULES.md. Q_in missing → held with note "pump-out only X min". `volume_is_total=True` → assumption "total volume used as working volume". Q_in >= Q_out → flagged "pumps cannot keep up with inflow" (no cycle time computed).

**R4 relief valve**: both conditions checked; message names which failed (both if both). Pressures converted to bar(g) by `units.py`.

**R5 design pressure**: `shutoff_head` may be printed as a pressure (bar, kg/cm2 ...) or as a head in m; a pressure is used as is, a head is converted (the RULES.md test case "shut-off 9.0" is 9.0 bar). If `max_suction` and `shutoff_head` are both present, the pump basis is used (it wins over the margin basis) and stated. Head in m → bar via `rules.yaml` factor x SG; `service == "water"` → SG 1.0 with the assumption; other service with no `sg` → held. Else margin basis `max(factor x operating, operating + adder)`.

**R6 dose**: as RULES.md. `%` without w/w or w/v → held. w/w without density → held ("no default density").

**Numbers**: no rounding inside the engine. Comparisons use `math.isclose(rel_tol=1e-9)` for equality at the limit (a value equal to the limit passes). Display rounding (2 decimals) happens only in messages.

## 4. Units (`units.py`)

`to_base(quantity, value, unit) -> (number, assumptions)` or raises `UnknownUnit`. Base units: flow m3/h, pressure bar(g), head m, length m, volume m3, concentration mg/L, strength fraction, density kg/L, count.

- Normalise before lookup: lower-case, strip spaces and dots, superscripts to digits (m³/h → m3/h, kg/cm² → kg/cm2), "hr" = "h".
- Every factor from the RULES.md Units table lives in `rules.yaml` `units:`, including 1.013 and the aliases (m3/hr, cum/hr, cu.m/hr; barg; DN; cum; ppm); `units.py` holds the parsing, not the numbers. A "÷N" row is stored as its reciprocal and the yaml ↔ doc test compares 1/N within the 1e-9 tolerance.
- **Absolute pressure:** any pressure unit marked `(a)` / `a` (bar a, bara, kg/cm2(a), kPa a, psia) → convert, then subtract 1.013 bar. Unmarked → gauge, with the assumption stated. Claude Code adds the `bar(a)/bara`, `kPa(a)`, `psia` rows to the RULES.md Units table in the same commit (R4 already says "bar a, kPa a" but the table lacks them).
- NPS inches → NB by the table; a size not in the table → UnknownUnit.
- `"1W+1S"`, `"2W+1S"`, `"2W"` → `{working, standby}`; anything else → UnknownUnit.
- Unknown unit → `UnknownUnit`; the engine turns it into **held**, message names the input and the unit as printed.

## 5. Verdict (`app/verdict/verdict.py`)

```python
verdict(results: list[RuleResult], disagreements: list[dict], clashes: list[dict], pages_checked: int) -> dict
# -> {"verdict": "BLOCK" | "REVIEW" | "no conflicts found", "label": str, "reasons": [str]}
# verdict strings match EVAL.md §2 expected_verdict exactly, so keys and outputs compare directly

proven(before: list[RuleResult], after: list[RuleResult], clashes: list[dict]) -> dict
# -> {"proven": bool, "reasons": [str]}
```

- `verdict`: any flagged, any disagreement, or any clash → BLOCK; else any held → REVIEW; else "no conflicts found" with label `"No conflicts found in {N} pages checked"`. Reasons list every flagged/held rule, disagreement and clash.
- `proven`: no flagged in `after`; no held in `after` whose `rule_id` was not held in `before`; no clashes. Notes never block.
- `disagreements` and `clashes` are plain dicts (`{"attribute", "values": [{file, page, value}]}` and `{"entry_id", "attribute", "approved", "proposed"}`); phase 2 builds the first, the register check (phase 2, step 7b) the second. Phase 1 only consumes them.
- The word "PASS" never appears in any output (tested).

## 6. `rules.yaml`

```yaml
version: 1
tolerance_rel: 1.0e-9
rules:
  R1:
    name: Pipe velocity
    live: true
    defaults:
      max_velocity: {value: 3.0, unit: m/s, confirm: true}
    schedule_id_mm:
      100: {sch40: 102.3, sch80: 97.2}
      150: {sch40: 154.1, sch80: 146.3}
      200: {sch40: 202.7, sch80: 193.7}
    solids_services: [slurry, sludge, ash, "waste water", backwash]
  R2: {name: Standby available, live: true, defaults: {standby_required: {value: 1, unit: count, confirm: true}}}
  R3: {name: Sump cycle time, live: true, defaults: {max_starts_per_hour: {value: 6, unit: 1/h, confirm: true}}}
  R4: {name: Relief valve setting, live: false, defaults: {operating_to_set_max: {value: 0.90, unit: ratio, confirm: true}}}
  R5: {name: Design pressure, live: false, defaults: {margin_factor: {value: 1.10, unit: ratio, confirm: true}, margin_adder: {value: 1.0, unit: bar, confirm: true}}}
  R6: {name: Chemical dose within pump range, live: false, defaults: {}}
units:
  atm_bar: 1.013
  head_m_to_bar_per_sg: 0.0981
  flow:     {m3/h: 1, m3/d: 0.0416666667, l/s: 3.6, l/min: 0.06, l/h: 0.001}
  pressure: {bar: 1, kg/cm2: 0.980665, kpa: 0.01, mpa: 10, psi: 0.0689476}
  nps_to_nb: {2: 50, 3: 80, 4: 100, 6: 150, 8: 200, 10: 250, 12: 300}
  inch_to_m: 0.0254
```

The solids list is a starting point; Bhargavi confirms it with the CONFIRM values (add a row to the RULES.md confirmed table: "R1 solids-bearing services"). `confirm: true` flips to `false` once she confirms; the value changes if she corrects it.

## 7. Tests

1. **Every RULES.md test case**, one parametrized case each, in `tests/rules/test_rN_*.py`, asserting status and the number to 2 decimals. R1 cases pass the D5-200 bands as `DocLimit`s (50-150 mm: 1.8-2.4; 200+: 2.1-2.5).
2. **Count guard** (`test_rules_match_doc.py`): parses each `## Rn` section's "Test cases" bullets in RULES.md and asserts the number of parametrized cases for Rn equals the number of bullets. A case added to the doc without a test fails.
3. **yaml ↔ doc** (`test_rules_match_doc.py`): rule ids in RULES.md headings == ids in `rules.yaml`; each default equals the "Confirmed value" column of the RULES.md confirmed table when filled, else the "Default above" column; every factor in the RULES.md Units table equals the `rules.yaml` factor; the schedule ID table matches.
4. **Units**: one test per table row, plus superscripts/spacing, unknown unit → UnknownUnit, `%` without w/w or w/v → held, absolute pressure subtracts 1.013.
5. **Held behaviour**: missing input, `evidence_ok=False`, `Disputed` input, unknown unit — each gives held with the input named.
6. **Verdict / proven**: BLOCK by flagged, by disagreement, by clash; REVIEW by held; "no conflicts found" label contains N; every verdict string is one of the three EVAL.md `expected_verdict` values; "PASS" never in any output; proven allows pre-existing held, refuses new held, refuses any clash, ignores notes.
7. **No model calls** (`test_no_model_calls.py`): AST-scan every `.py` in `app/rules/` and `app/verdict/`; fail on any import of `google`, `genai`, `httpx`, `requests`, `urllib`, `socket`, `app.store`.
8. **No hard-coded limits**: `checks.py` and `units.py` contain no numeric literal other than 0, 1, 2, 60, 1000, 3600 and pi-related (`math.pi`) — asserted by a simple AST scan of numeric constants.
9. `pytest -q` green, including the 5 phase 0 tests.

## Doc updates Claude Code makes in this phase (same commit as the code they describe)

Found by cross-checking this spec against the owner docs:

1. **RULES.md R1**: low-velocity wording (§3 above).
2. **RULES.md Units**: absolute-pressure rows (§4 above).
3. **RULES.md "Every result carries"**: add `unit` and `notes` (information only, never changes status), and inputs carry `file` as well as `page`, `quote`, `unit`.
4. **RULES.md confirmed table**: add the row "R1 solids-bearing services".
5. **ARCHITECTURE.md §5 value record**: `{item, attribute, value, unit, file, page, quote, evidence_ok}`. `file` is missing today; a plant has many files and EVAL keys already use `{file, page}`.
6. **EVAL.md §2 key formats for sets B and F** (only the change format exists today):
   - B: `{"id": "B1", "item": "...", "file": "Part3.pdf", "page": 146, "label_text": "...", "found": true, "box": [x0, y0, x1, y1]}`, box normalised 0-1 from the text layer; the absent item has `"found": false` and no box.
   - F: `{"id": "F1", "calculation": "R1 velocity ...", "inputs": [{"name": "...", "value": 105, "unit": "m3/h", "file": "...", "page": 57, "quote": "..."}], "expected": {"value": 3.71, "unit": "m/s", "status": "flagged"}}`.

## Build order inside the phase (if time runs short, the tail waits)

1. `model.py`, `units.py`, `rules.yaml`, R1-R3, `verdict.py` and their tests (the live rules).
2. R4-R6 and their tests.
3. Count guard, yaml ↔ doc, no-model-calls, no-hard-coded-limits tests.
4. `find_pages.py`, `label_positions.py` (needed by Bhargavi for the keys, so start them as soon as 1 is green).

## Bhargavi does herself (in parallel, ~25 min)

1. **CONFIRM values** (RULES.md confirmed table: confirmed value + one-line reason): R1 3.0 m/s, R1 solids services list, R2 1, R3 6/h, R4 0.90, R5 1.10 / 1.0 bar. Tell Claude Code the answers; it records them and flips `confirm`.
2. **Set A keys** `eval/keys/A1-A3.json` (floor wash SG U1, PT filter backwash, MRS U1 waste water): run `python scripts/find_pages.py "floor wash" "FW pump" ...` with every name you know; open every hit plus every P&ID and data-sheet page of that system; write the pages and values you confirm. Script hits are proposals, never the key.
3. **Set B keys** `eval/keys/B1-B5.json`: `python scripts/label_positions.py data/bhel/Part3.pdf 146 "<label text>"` gives the label box from the text layer; you check each one on the page. B5 (SG Unit-3) key = "not found".
4. **Set F keys** `eval/keys/F1-F3.json`: read the inputs off the pages yourself, work each by hand (e.g. floor-wash discharge velocity vs D5-200), commit.
5. Commit A, B, F keys **before phase 2 runs anything** on them.

## Out of scope

Reading documents, the evidence check itself, the register store, Firestore, any API route, any screen change, any model call. R4-R6 live wiring.

## Done when

- [ ] `pytest -q` passes: every RULES.md test case, the count guard, yaml ↔ doc, units, held, verdict/proven, no-model-calls, no-hard-coded-limits.
- [ ] The six doc updates above are made, each in the commit with its code.
- [ ] Every CONFIRM value confirmed or corrected by Bhargavi and recorded in the RULES.md table; `confirm: false` in `rules.yaml` for each.
- [ ] `eval/keys/A1-A3`, `B1-B5`, `F1-F3` committed by Bhargavi, before phase 2.
- [ ] `PHASES.md` phase 1 Status `done (phase-1-rules)`; tag pushed.
