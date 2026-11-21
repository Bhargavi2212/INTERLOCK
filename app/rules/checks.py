"""One function per rule, as RULES.md. Limits come only from rules.yaml or a DocLimit.

Each check takes (ins, rule_cfg, rules, doc_limits) and returns a RuleResult.
A missing or unusable input raises HeldInput (engine turns it into held).
No rounding here except in messages; comparisons use the rules.yaml tolerance.
"""

from __future__ import annotations

import math

from app.rules.engine import HeldInput, default_limit
from app.rules.model import RuleResult
from app.rules.units import UnknownUnit, matches_phrase, normalise, parse_arrangement

FORMULAS = {
    "R1": "v = (Q / 3600) / (pi/4 * D^2)",
    "R2": "installed >= working + standby_required",
    "R3": "t_cycle_min = (V / Q_in + V / (Q_out - Q_in)) * 60 >= 60 / max_starts_per_hour",
    "R4": "operating <= ratio * set and set <= design",
    "R5": "design >= max_suction + shutoff_head, else design >= max(factor * operating, operating + adder)",
    "R6": "kg/h = dose * Q / 1000; L/h = kg/h / (strength * density) [w/w] or kg/h / strength [w/v]; pump_min <= L/h <= pump_max",
}


def _tol(rules: dict) -> float:
    return rules["tolerance_rel"]


def _gt(a: float, b: float, tol: float) -> bool:
    """a > b, treating values equal within tolerance as equal (equal passes)."""
    return a > b and not math.isclose(a, b, rel_tol=tol)


def _lt(a: float, b: float, tol: float) -> bool:
    return a < b and not math.isclose(a, b, rel_tol=tol)


def _optional_text(ins, name: str) -> str | None:
    """Optional text input; unusable counts as unstated (used where never held)."""
    if not ins.has(name):
        return None
    try:
        return ins.text(name) or None
    except HeldInput:
        return None


def _result(rule_id, rule_cfg, status, value, unit, limit, limit_source, message, assumptions=None, notes=None):
    return RuleResult(
        rule_id=rule_id, status=status, value=value, unit=unit, limit=limit,
        limit_source=limit_source, formula=FORMULAS[rule_id], inputs={},
        message=f"{rule_id} {rule_cfg['name']}: {message}",
        assumptions=assumptions or [], notes=notes or [],
    )


# ---------------------------------------------------------------- R1 velocity

def r1_velocity(ins, rule_cfg, rules, doc_limits):
    tol = _tol(rules)
    units = rules["units"]
    assumptions, notes = [], []

    # Q
    if ins.has("flow_total"):
        q = ins.num("flow_total")
    elif ins.has("flow_per_pump"):
        per = ins.num("flow_per_pump")
        if not ins.has("pumps_into_line"):
            raise HeldInput("pumps_into_line", "missing: documents do not state in text whether the pumps share one discharge line")
        n = ins.num("pumps_into_line")
        q = per * n
        if n > 1:
            assumptions.append("upper bound for parallel pumps on a shared header (real operating point is lower)")
    else:
        raise HeldInput("flow", "missing (flow_total or flow_per_pump)")

    # D
    nb = ins.num("line_nb") if ins.has("line_nb") else None
    if ins.has("line_id"):
        d = ins.num("line_id")
    elif nb is not None:
        sch = (_optional_text(ins, "schedule") or "").lower().replace(" ", "")
        table = rule_cfg["schedule_id_mm"]
        nb_key = int(nb) if float(nb).is_integer() else None
        if sch in ("sch40", "sch80") and nb_key in table:
            d = table[nb_key][sch] * units["mm_to_m"]
            assumptions.append(f"internal diameter {table[nb_key][sch]} mm from the {sch} table")
        else:
            d = nb * units["nb_to_m"]
            assumptions.append(
                "nominal bore used as internal diameter (slightly over-states velocity for Sch 40, "
                "under-states it for Sch 80 and heavier)")
    else:
        raise HeldInput("line_nb", "missing: no line size (line_nb or line_id)")

    v = (q / 3600) / (math.pi / 4 * d ** 2)

    # Limit: a document band whose applies_to matches the line's role (roles most
    # specific first); role unstated -> assumed pump discharge (stricter).
    roles = rule_cfg["line_roles"]
    role_text = _optional_text(ins, "line_role")
    role = rule_cfg["assumed_line_role"] if role_text is None else matches_phrase(role_text, roles)
    band = None
    if role is not None and nb is not None:
        for dl in doc_limits:
            if (dl.rule_id == "R1" and dl.evidence_ok and dl.high is not None and dl.covers_nb(nb)
                    and normalise(dl.unit) in units["velocity"]
                    and matches_phrase(dl.applies_to, roles) == role):
                band = dl
                break
    if band is not None:
        limit, source = band.high, band.citation()
        if role_text is None:
            assumptions.append(f"line assumed to be {role}")
    elif role == rule_cfg["suction_line_role"]:
        limit, source = default_limit(rule_cfg, "max_velocity_suction")
    else:
        limit, source = default_limit(rule_cfg, "max_velocity")

    status = "flagged" if _gt(v, limit, tol) else "OK"
    msg = f"v = {v:.2f} m/s vs limit {limit:.2f} m/s ({source}); inputs {ins.pages()}"

    # Low side: never held
    if band is not None and band.low is not None and _lt(v, band.low, tol):
        service = _optional_text(ins, "service")
        solids = rule_cfg["solids_services"]["value"]
        if service and matches_phrase(service, solids):
            status = "flagged"
            msg += f"; below the documents' lower value {band.low:.2f} m/s for solids-bearing service '{service}'"
        elif service:
            notes.append(f"below the documents' lower value {band.low:.2f} m/s, information only")
        else:
            notes.append(
                f"below the documents' lower value {band.low:.2f} m/s; "
                "solids check not run: service type not stated")

    return _result("R1", rule_cfg, status, v, "m/s", limit, source, msg, assumptions, notes)


# ---------------------------------------------------------------- R2 standby

def r2_standby(ins, rule_cfg, rules, doc_limits):
    tol = _tol(rules)
    assumptions = []
    arr = None
    needed = not (ins.has("installed") and ins.has("working") and ins.has("standby_required"))
    if ins.has("arrangement") and needed:
        text = ins.text("arrangement")
        try:
            arr = parse_arrangement(text)
        except UnknownUnit as e:
            raise HeldInput("arrangement", str(e)) from None

    if ins.has("installed") or arr is None or "installed" not in arr:
        installed = ins.num("installed")
    else:
        installed = float(arr["installed"])
        assumptions.append("installed count taken from the arrangement")

    if ins.has("working"):
        working = ins.num("working")
    elif arr is not None:
        working = float(arr["working"])
        assumptions.append("working count taken from the arrangement")
    else:
        raise HeldInput("working", "missing")

    if ins.has("standby_required"):
        standby = ins.num("standby_required")
        source = f"stated ({ins.pages()})"
    elif arr is not None and ins.raw["arrangement"].source in ("document", "register"):
        # standby comes only from the documents' (or an approved) arrangement, never a change or fix
        standby = float(arr["standby"])
        v = ins.raw["arrangement"]
        where = f"{v.file} p.{v.page}" if v.source == "document" else "register"
        source = f"arrangement '{v.value}' ({where})"
    else:
        standby, source = default_limit(rule_cfg, "standby_required")
        assumptions.append("continuous duty assumed")

    required = working + standby
    status = "flagged" if _lt(installed, required, tol) else "OK"
    sign = "<" if status == "flagged" else ">="
    msg = (f"installed {installed:g} {sign} working {working:g} + standby {standby:g}; "
           f"standby from {source}; inputs {ins.pages()}")
    return _result("R2", rule_cfg, status, installed, "count", required, source, msg, assumptions)


# ---------------------------------------------------------------- R3 sump cycle

def r3_sump(ins, rule_cfg, rules, doc_limits):
    tol = _tol(rules)
    assumptions = []
    vol = ins.num("volume")
    q_out = ins.num("q_out")
    if q_out <= 0:
        raise HeldInput("q_out", f"must be > 0 (got {q_out:g} m3/h)")
    if ins.has("volume_is_total") and ins.flag("volume_is_total"):
        assumptions.append("total volume used as working volume")

    if not ins.has("q_in"):
        pump_out = vol / q_out * 60
        raise HeldInput("q_in", "missing (inflow not stated)",
                        notes=[f"pump-out only {pump_out:.1f} min, information only"])
    q_in = ins.num("q_in")
    if q_in <= 0:
        raise HeldInput("q_in", f"must be > 0 (got {q_in:g} m3/h)")

    starts, source = default_limit(rule_cfg, "max_starts_per_hour")
    limit = 60 / starts

    if q_in > q_out or math.isclose(q_in, q_out, rel_tol=tol):
        msg = f"pumps cannot keep up with inflow (Q_in {q_in:g} >= Q_out {q_out:g} m3/h); inputs {ins.pages()}"
        return _result("R3", rule_cfg, "flagged", None, "min", limit, source, msg, assumptions)

    t = (vol / q_in + vol / (q_out - q_in)) * 60
    status = "flagged" if _lt(t, limit, tol) else "OK"
    msg = f"cycle {t:.1f} min vs minimum {limit:.1f} min ({source}); inputs {ins.pages()}"
    return _result("R3", rule_cfg, status, t, "min", limit, source, msg, assumptions)


# ---------------------------------------------------------------- R4 relief valve

def r4_relief(ins, rule_cfg, rules, doc_limits):
    tol = _tol(rules)
    op = ins.num("operating")
    set_p = ins.num("set")
    design = ins.num("design")
    ratio, source = default_limit(rule_cfg, "operating_to_set_max")
    margin_limit = ratio * set_p

    failures = []
    if op > set_p or math.isclose(op, set_p, rel_tol=tol):
        failures.append(f"set {set_p:g} at or below operating {op:g} bar(g): the valve lifts in normal operation")
    elif _gt(op, margin_limit, tol):
        failures.append(f"operating {op:g} > {ratio:g} x set = {margin_limit:.2f} bar(g): the valve simmers")
    if _gt(set_p, design, tol):
        failures.append(f"set {set_p:g} above design {design:g} bar(g): item not protected")

    status = "flagged" if failures else "OK"
    msg = "; ".join(failures) if failures else (
        f"operating {op:g} <= {margin_limit:.2f} and set {set_p:g} <= design {design:g} bar(g)")
    return _result("R4", rule_cfg, status, op, "bar(g)", margin_limit, source,
                   f"{msg}; inputs {ins.pages()}")


# ---------------------------------------------------------------- R5 design pressure

def _shutoff_bar(ins, rules) -> float:
    """Shut-off as a pressure, or a head in m converted with SG (water rule)."""
    from app.rules.units import normalise

    v = ins._value("shutoff_head")
    if normalise(v.unit) != "m":
        return ins.num("shutoff_head", "pressure")
    head = ins.num("shutoff_head", "head")
    if ins.has("sg"):
        sg = ins.num("sg")
    else:
        service = _optional_text(ins, "service")
        water = rules["rules"]["R5"]["water_services"]["value"]
        solids = rules["rules"]["R1"]["solids_services"]["value"]
        if service and matches_phrase(service, water) and not matches_phrase(service, solids):
            sg = 1.0
            ins.assumptions.append(f"SG 1.0 for water service '{service}'")
        else:
            why = f"service '{service}' is not a water service" if service else "service not stated"
            raise HeldInput("sg", f"missing: head in m needs SG ({why}; no default SG)")
    return head * rules["units"]["head_m_to_bar_per_sg"] * sg


def r5_design_pressure(ins, rule_cfg, rules, doc_limits):
    tol = _tol(rules)
    design = ins.num("design")
    if ins.has("max_suction") and ins.has("shutoff_head"):
        suction = ins.num("max_suction")
        shutoff = _shutoff_bar(ins, rules)
        required = suction + shutoff
        basis = f"pump basis: max suction {suction:g} + shut-off {shutoff:.2f} bar(g)"
        source = f"stated ({ins.pages()})"
    elif ins.has("operating"):
        op = ins.num("operating")
        factor, src_f = default_limit(rule_cfg, "margin_factor")
        adder, _ = default_limit(rule_cfg, "margin_adder")
        required = max(factor * op, op + adder)
        basis = f"margin basis: max({factor:g} x {op:g}, {op:g} + {adder:g})"
        source = src_f
    else:
        raise HeldInput("operating", "missing (and no max_suction + shutoff_head)")

    status = "flagged" if _lt(design, required, tol) else "OK"
    msg = f"design {design:g} vs required {required:.2f} bar(g) ({basis}); inputs {ins.pages()}"
    return _result("R5", rule_cfg, status, design, "bar(g)", required, source, msg, [basis])


# ---------------------------------------------------------------- R6 chemical dose

def r6_dose(ins, rule_cfg, rules, doc_limits):
    from app.rules.units import strength_kind

    tol = _tol(rules)
    dose = ins.num("dose")
    q = ins.num("flow")
    strength = ins.num("strength")
    kind = strength_kind(ins.raw["strength"].unit)
    kg_h = dose * q / 1000
    if kind == "w/w":
        if not ins.has("density"):
            raise HeldInput("density", "missing: strength is w/w and there is no default density")
        l_h = kg_h / (strength * ins.num("density"))
    else:
        l_h = kg_h / strength

    lh_to_m3h = rules["units"]["flow"]["l/h"]
    pump_min = ins.num("pump_min") / lh_to_m3h
    pump_max = ins.num("pump_max") / lh_to_m3h

    if _lt(l_h, pump_min, tol):
        status, why = "flagged", f"below pump minimum {pump_min:g} L/h"
        limit = pump_min
    elif _gt(l_h, pump_max, tol):
        status, why = "flagged", f"above pump maximum {pump_max:g} L/h"
        limit = pump_max
    else:
        status, why = "OK", f"within pump range {pump_min:g}-{pump_max:g} L/h"
        limit = pump_max
    msg = f"{kg_h:.2f} kg/h active -> {l_h:.2f} L/h ({kind}), {why}; inputs {ins.pages()}"
    return _result("R6", rule_cfg, status, l_h, "L/h", limit, f"pump range ({ins.pages()})", msg)


CHECKS = {
    "R1": r1_velocity,
    "R2": r2_standby,
    "R3": r3_sump,
    "R4": r4_relief,
    "R5": r5_design_pressure,
    "R6": r6_dose,
}
