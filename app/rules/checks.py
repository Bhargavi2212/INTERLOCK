"""One function per rule, as RULES.md. Limits come only from rules.yaml or a DocLimit.

Each check takes (ins, rule_cfg, rules, doc_limits) and returns a RuleResult.
A missing or unusable input raises HeldInput (engine turns it into held).
No rounding here except in messages; comparisons use the rules.yaml tolerance.
"""

from __future__ import annotations

import math

from app.rules.engine import HeldInput, default_limit
from app.rules.model import RuleResult
from app.rules.units import UnknownUnit, matches_phrase, parse_arrangement

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
            raise HeldInput("pumps_into_line", "missing: documents do not show how many pumps run into this line")
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

    # Limit: document band for pump discharge (role unstated -> band, with assumption)
    band_role = rule_cfg["band_line_role"]
    role = _optional_text(ins, "line_role")
    role_ok = role is None or matches_phrase(role, [band_role]) is not None
    band = None
    if role_ok and nb is not None:
        for dl in doc_limits:
            if dl.rule_id == "R1" and dl.evidence_ok and dl.high is not None and dl.covers_nb(nb):
                band = dl
                break
    if band is not None:
        limit, source = band.high, band.citation()
        if role is None:
            assumptions.append(f"line assumed to be {band_role}")
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
    installed = ins.num("installed")

    arr = None
    if ins.has("arrangement"):
        text = ins.text("arrangement")
        try:
            arr = parse_arrangement(text)
        except UnknownUnit as e:
            raise HeldInput("arrangement", str(e)) from None

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
    elif arr is not None:
        standby = float(arr["standby"])
        v = ins.raw["arrangement"]
        source = f"arrangement '{v.value}' ({v.file} p.{v.page})" if v.source == "document" else f"arrangement '{v.value}' ({v.source} text)"
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


CHECKS = {
    "R1": r1_velocity,
    "R2": r2_standby,
    "R3": r3_sump,
}
