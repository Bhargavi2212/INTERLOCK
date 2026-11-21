# Rules

The engineering checks the rule engine (`app/rules/`) runs. **This file is the single source of every formula, limit and unit factor.** `app/rules/rules.yaml` must match it exactly; a test enforces that.

The rule engine never calls a model. Same inputs, same outputs, every run.

**Where a limit comes from, in order:**
1. **The plant's own documents**, when they state it (the result cites that page). Example: BHEL D5-200 sets pump discharge velocity at 1.8-2.4 m/s for 50-150 mm pipe. Argon reads these design-basis limits in phase 2 as values with `page`, `quote` and `unit`, through the same evidence check as every other value.
2. **The default here**, marked **CONFIRM** until Bhargavi confirms or corrects it in phase 1 (recorded in the table at the end of this file). Used only when no document limit is found for that rule and that case (e.g. no band covers the line size), and the result says so.

Live in the demo today: **R1, R2, R3**. R4-R6 are built and unit-tested; wired live only if phase 2 finishes early.

---

## Result statuses

| Status | Meaning |
|---|---|
| **OK** | All inputs present, check passed |
| **flagged** | All inputs present, check failed. Message cites the rule, the limit's source and the input pages |
| **held** | A required input is missing or ambiguous. Message names it |

Every result carries: `rule_id`, `status`, `value`, `unit`, `limit`, `limit_source`, `formula`, `inputs`, `message`, `assumptions`, `notes` (information only; never changes the status).

**Inputs.** Each input carries `source`, `file`, `page`, `quote`, `unit`. `source` is `document` (read from a page; must pass the evidence check), `change` (from the change text), `fix` (from an agent fix) or `register` (an approved change, overlaid on the as-issued values); for `change`, `fix` and `register`, `quote` is that text (or the register entry) and `file`/`page` are empty. Text and yes/no inputs (`service`, `line_role`, `schedule`, `arrangement`, `volume_is_total`) may have an empty unit, and so may `sg` (specific gravity, dimensionless); any other number with an empty unit is **held**. A physical quantity ≤ 0 (flow, size, diameter, volume, concentration, strength, density, velocity, head, SG) is **held**, naming the input; gauge pressure and counts may be 0.

**Phrase lists** (`solids_services`, `water_services`, the pump-discharge line role) match case-insensitively as **whole phrases** bounded by word boundaries, never as bare substrings (`ash` does not match `wash`).

## Verdict

- Any **flagged** result, documents that disagree about a changed value (the caller passes only disagreements about values the change touches), or a **clash with an approved change in the register** → **BLOCK**
- Otherwise any **held** result → **REVIEW**
- Otherwise → **No conflicts found in N pages checked** (never "PASS")

**Proven (a proposed fix):** the server re-runs every live rule and the register check on the fixed values. Proven = no **flagged** results, no **new held** results (held results that were already held before the fix may remain), and no register clash. Information-only notes (such as velocity below a range's lower value) never block. A rule that ran before the fix but not after it is a reason, so the fix is not proven.

## Numbers

- Comparisons use a relative tolerance of 1e-9 (so 0.36 x 60 = 21.6 counts as 21.6).
- Test cases assert to 2 decimals.

---

## R1 Pipe velocity

- **Formula:** `v = (Q / 3600) / (pi/4 * D^2)`; Q in m3/h, D in m, v in m/s.
- **D:** the internal diameter when the documents state it (or a schedule, from the table below). Otherwise the nominal bore in metres (100 NB → 0.100 m), stated as an assumption. For Sch 40 this slightly **over**-states velocity; for Sch 80 and heavier it **under**-states it.

  | NB | Sch 40 ID (mm) | Sch 80 ID (mm) |
  |---|---|---|
  | 100 | 102.3 | 97.2 |
  | 150 | 154.1 | 146.3 |
  | 200 | 202.7 | 193.7 |

- **Q:** rated flow per pump x number of pumps running into that line. For parallel pumps on a shared header this is an **upper bound** (the real operating point is lower); stated on the result.
- **Limits:**
  - From the plant's documents when stated (BHEL D5-200, pump discharge: 50-150 mm 1.8-2.4 m/s; 200 mm and above 2.1-2.5 m/s). The **upper value is the check**; below the lower value is shown as information only.
  - Default when the documents state none: max 3.0 m/s (**CONFIRM**).
  - **Line roles** (input `line_role`): `discharge header`, `pump suction`, `pump discharge` (matched most specific first). A document band is used only if its `applies_to` matches the line's role and its unit is m/s; a header line uses the documents' header row. Role unstated → treated as pump discharge (stricter), with the assumption "line assumed to be pump discharge".
  - **Defaults** when no document band applies (role stated as something else, or no band covers the size): pump suction max 1.8 m/s (**CONFIRM**); any other line 3.0 m/s.
  - **Low side:** service matching a `solids_services` phrase and v below the band's lower value → **flagged**. Not solids → note "below the documents' lower value, information only". Service unstated → the note gives both facts (below the lower value; solids check not run, service not stated). The low side never makes the result held.
- **Held if:** flow or line size missing; or the documents do not show whether the pumps share one discharge line.
- **Test cases (limit 2.4 m/s for 50-150 mm, 2.5 m/s for 200 mm and above, nominal bore as D):**
  - 105 m3/h, 100 NB → 3.71 m/s → **flagged**
  - 210 m3/h, 100 NB → 7.43 m/s → **flagged**
  - 210 m3/h, 150 NB → 3.30 m/s → **flagged**
  - 210 m3/h, 200 NB → 1.86 m/s → **OK** (below 2.1, shown as information)
  - 105 m3/h, 150 NB → 1.65 m/s → **OK** (below 1.8, information)
  - 105 m3/h, 100 NB, Sch 40 ID 102.3 mm → 3.55 m/s → **flagged**
  - 105 m3/h, no line size → **held**

## R2 Standby available

- **Rule:** `installed >= working + standby_required`.
- **standby_required:** from the documents' arrangement when stated (e.g. "1W+1S"); otherwise default 1 with the assumption "continuous duty assumed". **Never from the change or a fix**: a changed arrangement ("2W+1S", "3W") sets only the working count.
- **arrangement** (`NW+MS` or `NW`) supplies the standby count, and the working count only when `working` is missing. When the two disagree, that is a disagreement the caller passes to the verdict; R2 does not decide it.
- **Documents disagree on a requirement:** if documents disagree on a required count or limit (e.g. standby required), use the stricter value, state it as an assumption naming both pages, and still pass the disagreement to the verdict. Disputed measured values (flow, size, volume, installed count) remain held. **Applied to `standby_required` only for now.**
- **Held if:** installed or working count missing.
- **Test cases:**
  - installed 2, working 2 → **flagged**
  - installed 3, working 2 → **OK**
  - installed 2, working 1 → **OK**

## R3 Sump cycle time

- **Formula:** `t_cycle_min = (V / Q_in + V / (Q_out - Q_in)) * 60`.
  - V = **working volume** between pump start and stop levels, m3. If only total volume is stated, use it and state the assumption.
  - Q_in = inflow, Q_out = pumping rate, m3/h.
- **Flagged if:** Q_in >= Q_out ("pumps cannot keep up with inflow"), or t_cycle below the limit.
- **Limit:** `t_cycle >= 60 / max_starts_per_hour`. Default 6 starts/h → 10 min (**CONFIRM**).
- **Held if:** volume or Q_out missing; or Q_in missing (then show pump-out-only time `V / Q_out * 60` as information); or Q_in ≤ 0 or Q_out ≤ 0 (the input is named).
- **Test cases:**
  - V 105, Q_out 210, Q_in missing → **held** (pump-out only 30.0 min)
  - V 105, Q_out 210, Q_in 100 → 63.0 + 57.3 = 120.3 min → **OK**
  - V 10, Q_out 60, Q_in 50 → 12.0 + 60.0 = 72.0 min → **OK**
  - V 2, Q_out 60, Q_in 30 → 4.0 + 4.0 = 8.0 min → **flagged** (< 10)
  - V 10, Q_out 60, Q_in 60 → **flagged** (cannot keep up)

## R4 Relief valve setting

- **Rule:** `operating <= 0.90 * set` and `set <= design` of the protected item (**CONFIRM** 0.90).
- **Flags:** set too close to (or below) operating — the valve lifts or simmers in normal operation; set above design — item not protected.
- **Pressures are gauge.** Absolute values (bar a, kPa a) are converted by subtracting 1.013 bar. A pressure with no g/a marking is assumed gauge and stated as an assumption.
- **Held if:** set, operating or design pressure missing.
- **Test cases:**
  - operating 30, set 22, design 40 → **flagged** (lifts in normal operation)
  - operating 30, set 35, design 40 → **OK** (30 ≤ 31.5)
  - operating 30, set 32, design 40 → **flagged** (30 > 28.8, simmers)
  - operating 30, set 45, design 40 → **flagged** (above design)

## R5 Design pressure

- **Rule (pump discharge lines):** `design >= max_suction + shutoff_head` when the documents state them. Head in m is converted to bar by the Units table (SG rule there).
- **Rule (otherwise):** `design >= max(1.10 * operating, operating + 1.0)` bar(g) (**CONFIRM** both), stated as the basis used.
- **Held if:** design pressure missing, or neither basis has its inputs.
- **Test cases:**
  - operating 5.0, design 6.0 → required 6.0 → **OK**
  - operating 5.0, design 5.5 → required 6.0 → **flagged**
  - suction 0.5, shut-off 9.0, design 8.0 → required 9.5 → **flagged**

## R6 Chemical dose within pump range

- **Formula:** `kg_per_h = dose_mg_per_L * Q_m3h / 1000` (dose as active chemical).
  - Strength % w/w: `L_per_h = kg_per_h / (strength * density)`.
  - Strength % w/v: `L_per_h = kg_per_h / strength` (no density).
- **Rule:** `pump_min <= L_per_h <= pump_max`.
- **Held if:** dose, flow, strength or pump range missing; or strength is w/w and density is missing (**no default density**: 10% hypochlorite is about 1.2 kg/L, and assuming 1.0 would be about 20% wrong).
- **Test cases:**
  - 2 mg/L, 500 m3/h, 10% w/v → 1.0 kg/h → 10.0 L/h; pump 21.6-444 L/h → **flagged** (below min)
  - 20 mg/L, 500 m3/h, 10% w/v → 100.0 L/h; pump 21.6-444 L/h → **OK**
  - 2 mg/L, 500 m3/h, 10% w/w, density 1.2 → 8.33 L/h; pump 0.5-5 L/h → **flagged** (above max)

---

## Units (exact factors)

Unknown units make the input **held**, never guessed. Superscripts and spacing are normalised (m³/h = m3/h).

| Quantity | Unit | To |
|---|---|---|
| Flow | m3/h, m3/hr, cum/hr, cu.m/hr | x1 m3/h |
| | m3/d | ÷24 m3/h |
| | L/s | x3.6 m3/h |
| | L/min | x0.06 m3/h |
| | L/h | x0.001 m3/h |
| Pressure | bar(g), barg | x1 bar(g) |
| | bar (no g/a marking) | x1 bar(g), assumed gauge, stated as an assumption |
| | kg/cm2(g) | x0.980665 bar(g) |
| | kg/cm2(a) | x0.980665, then subtract 1.013 → bar(g) |
| | kg/cm2 (no g/a marking) | x0.980665 bar(g), assumed gauge, stated |
| | kPa (no g/a marking) | x0.01 bar(g), assumed gauge, stated |
| | MPa (no g/a marking) | x10 bar(g), assumed gauge, stated |
| | psi, psig | x0.0689476 bar(g); psi with no marking assumed gauge, stated |
| | Absolute: an `(a)` marker, a separate `a` token ("bar a", "kPa a"), or the units bara, kpaa, kpa(a), psia | convert, then subtract 1.013 → bar(g) |
| Head | m (liquid column) | bar = m x 0.0981 x SG. SG 1.0 only when the service matches a `water_services` phrase and no `solids_services` phrase, stated as an assumption; otherwise, without a stated SG → **held** |
| Pipe size | NB / DN (mm) | ÷1000 m (nominal) |
| | NPS inches | by table: 2"=50, 3"=80, 4"=100, 6"=150, 8"=200, 10"=250, 12"=300 NB |
| Diameter | stated internal diameter in inches | x0.0254 m |
| | stated internal diameter in mm | ÷1000 m |
| Volume | m3, cum | x1 m3 |
| Count | count, nos, nos., no, number (case and dots ignored); a count is stated in its quote as digits or as a number word one to twelve ("Two" = 2), and when the quote has an arrangement NW+MS, installed = N + M ("Three (2W+1S) nos." → installed 3); arrangements `NW+MS` or `NW` for any N, M (e.g. 1W+2S, 3W) give working and standby counts (found anywhere in the printed text, first match wins: "Two (1W+1S) nos." → 1W+1S); `NXP%` (e.g. 3X100%, 2X50%) gives installed N, working ceil(100/P), standby N − working, parsed only when the arrangement is needed; anything else is unknown | dimensionless |
| Concentration | mg/L, ppm | x1 mg/L |
| Strength | % w/w, % w/v | fraction (10% → 0.10). A % with neither w/w nor w/v stated → **held** |
| Density | kg/L | x1 kg/L |
| Velocity | m/s, m/sec | x1 m/s |

## Adding a rule

1. Write it here first: formula, limit and its source, held-when, at least three test cases worked by hand.
2. Add it to `rules.yaml`.
3. Add the test cases to `tests/rules/`.
4. Explain it in the commit message.

## Confirmed values (phase 1)

| Rule | Default above | Confirmed value | Reason |
|---|---|---|---|
| R1 suction velocity max when documents state none | 1.8 m/s | | |
| R1 velocity max when documents state none | 3.0 m/s | 3.0 m/s | Common upper limit for water pump discharge when the plant states none |
| R2 standby default | 1 | 1 | Standard N+1 for continuous-duty pumps |
| R3 max pump starts per hour | 6 (10 min cycle) | 6 (10 min cycle) | Typical motor starting limit for small and medium pump motors |
| R4 operating / set margin | 0.90 | 0.90 | Keeps relief valves from simmering in normal operation |
| R5 margin factor / adder | 1.10 / 1.0 bar | 1.10 / 1.0 bar | The greater of 10% or 1 bar above operating |
| R1 solids-bearing services | slurry, sludge, ash, waste water, backwash | slurry, sludge, ash slurry, waste water, backwash | Services carrying suspended solids that settle at low velocity. "ash" replaced by "ash slurry": ash traces in floor wash do not settle at pump discharge velocities; settling applies to ash slurry service |
| R5 water services (SG 1.0) | water | water, raw water, clarified water, filtered water, DM water, service water, fire water, floor wash water | Water services where SG 1.0 is accurate |
