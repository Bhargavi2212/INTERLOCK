"""Step 6 scenario (no model): checked values -> rule inputs, as issued and after the change.

Mapping for the live rules (PHASE_2 section 6.6 and Amendments):
  R2  installed from documents; working / arrangement from the change when it
      changes them; standby from the arrangement (engine default otherwise).
  R1  flow_per_pump and line size from documents; pumps_into_line = the
      working count ONLY if a checked shared_discharge value says true, 1 if
      it says false, missing if absent (R1 held: "documents do not state in
      text whether the pumps share one discharge line"). service, line_role
      from documents.
  R3  volume, q_in from documents; q_out = flow_per_pump x working.
Several pages, same input:
  same value -> one Value (first cited; all listed in `sources`);
  different  -> Disputed, and a disagreement for the verdict when the change
                touches the input, or when `working` and `arrangement` disagree.
Register overlay: approved values replace as-issued values (source "register").
For pump items R1-R3 always run.
"""

from __future__ import annotations

from app.reading.evidence import norm
from app.rules.engine import INPUT_QUANTITY, load_rules
from app.rules.model import Disputed, DocLimit, Value
from app.rules.units import UnknownUnit, parse_arrangement, to_base

PUMP_RULES = ("R1", "R2", "R3")
RULE_INPUTS = {
    "R1": ("flow_total", "flow_per_pump", "pumps_into_line", "line_nb", "line_id", "schedule",
           "service", "line_role"),
    "R2": ("installed", "working", "standby_required", "arrangement"),
    "R3": ("volume", "q_out", "q_in", "volume_is_total"),
}


def _comparable(name: str, v: Value):
    """A value in comparable form (base units, parsed arrangement, normalised text)."""
    q = INPUT_QUANTITY.get(name, "text")
    if name == "arrangement":
        try:
            return tuple(sorted(parse_arrangement(v.value).items()))
        except UnknownUnit:
            return norm(v.value)
    if q in ("text", "bool"):
        return norm(v.value)
    try:
        return round(to_base(q if q != "pressure_or_head" else "pressure", v.value, v.unit,
                             load_rules()["units"])[0], 6)
    except UnknownUnit:
        return (norm(v.value), norm(v.unit))


def _doc_value(d: dict) -> Value:
    return Value(value=d["value"], unit=d.get("unit", "") or "", file=d["file"], page=int(d["page"]),
                 quote=d.get("quote", ""), evidence_ok=bool(d.get("evidence_ok", True)), source="document")


def merge_values(checked: list[dict], touched: set[str]) -> tuple[dict, list[dict], dict]:
    """-> (input -> Value | Disputed, disagreements, input -> [sources])."""
    groups: dict[str, list[Value]] = {}
    for d in checked:
        if d.get("evidence_ok") and d.get("input") in INPUT_QUANTITY:
            groups.setdefault(d["input"], []).append(_doc_value(d))

    merged, disagreements, sources = {}, [], {}
    for name, vals in groups.items():
        sources[name] = [{"file": v.file, "page": v.page, "value": v.value, "unit": v.unit} for v in vals]
        distinct = {}
        for v in vals:
            distinct.setdefault(_comparable(name, v), v)
        if len(distinct) == 1:
            merged[name] = vals[0]
        else:
            merged[name] = Disputed(tuple(distinct.values()))
            if name in touched:
                disagreements.append({"attribute": name, "values": [
                    {"file": v.file, "page": v.page, "value": v.value} for v in distinct.values()]})

    # working (data sheet) vs arrangement (scope) disagree -> a disagreement on working
    w, a = merged.get("working"), merged.get("arrangement")
    if isinstance(w, Value) and isinstance(a, Value):
        try:
            arr_working = parse_arrangement(a.value)["working"]
            w_count = to_base("count", w.value, w.unit, load_rules()["units"])[0]
            if arr_working != w_count and not any(d["attribute"] == "working" for d in disagreements):
                disagreements.append({"attribute": "working", "values": [
                    {"file": a.file, "page": a.page, "value": a.value},
                    {"file": w.file, "page": w.page, "value": w.value}]})
        except UnknownUnit:
            pass
    return merged, disagreements, sources


def _shared(shared_checked: list[dict]):
    """Checked shared_discharge values -> True / False / None (absent or disputed)."""
    vals = {bool(d["value"]) if not isinstance(d["value"], str) else d["value"].strip().lower() in ("true", "yes")
            for d in shared_checked if d.get("evidence_ok")}
    if len(vals) == 1:
        return vals.pop(), next(d for d in shared_checked if d.get("evidence_ok"))
    return None, None


def _count(v) -> float | None:
    if not isinstance(v, Value):
        return None
    try:
        return to_base("count", v.value, v.unit, load_rules()["units"])[0]
    except UnknownUnit:
        return None


def build_inputs(values: dict, shared, shared_src: dict | None) -> dict:
    """input name -> Value for R1-R3, deriving pumps_into_line and q_out."""
    by_rule = {r: {k: values.get(k) for k in RULE_INPUTS[r] if values.get(k) is not None} for r in PUMP_RULES}

    working = values.get("working")
    if working is None and isinstance(values.get("arrangement"), Value):
        try:
            n = parse_arrangement(values["arrangement"].value)["working"]
            a = values["arrangement"]
            working = Value(n, "count", file=a.file, page=a.page, quote=a.quote, source=a.source)
        except UnknownUnit:
            working = None

    # R1 pumps into the line
    if shared is True and working is not None:
        by_rule["R1"]["pumps_into_line"] = working
    elif shared is False and shared_src:
        by_rule["R1"]["pumps_into_line"] = Value(1, "count", file=shared_src["file"], page=int(shared_src["page"]),
                                                 quote=shared_src.get("quote", ""))
    else:
        by_rule["R1"].pop("pumps_into_line", None)

    # R3 pumping rate = per-pump flow x working
    per, n = values.get("flow_per_pump"), _count(working)
    if isinstance(per, Value) and n is not None:
        try:
            q = to_base("flow", per.value, per.unit, load_rules()["units"])[0] * n
            src = "change" if "change" in (per.source, getattr(working, "source", "")) else per.source
            by_rule["R3"]["q_out"] = Value(q, "m3/h", file=per.file, page=per.page,
                                           quote=f"{per.value} {per.unit} per pump x {n:g} working", source=src)
        except UnknownUnit:
            pass
    return by_rule


def change_values(changes: list[dict], change_text: str) -> dict:
    out = {}
    for c in changes:
        name = c.get("input")
        if name in INPUT_QUANTITY and c.get("to") not in (None, ""):
            out[name] = Value(c["to"], c.get("unit", "") or "", quote=change_text, source="change")
    # A changed arrangement gives the working count only; the standby requirement stays
    # the documents' arrangement or the default (RULES.md R2), so it is not passed on.
    arrangement = out.pop("arrangement", None)
    if arrangement is not None and "working" not in out:
        try:
            out["working"] = Value(parse_arrangement(arrangement.value)["working"], "count",
                                   quote=change_text, source="change")
        except UnknownUnit:
            pass
    return out


def register_values(entries: list[dict]) -> dict:
    out = {}
    for e in entries:
        if e.get("attribute") in INPUT_QUANTITY:
            out[e["attribute"]] = Value(e["value"], e.get("unit", "") or "",
                                        quote=f"approved change {e.get('entry_id', '')}", source="register")
    return out


def doc_limits(checked_limits: list[dict]) -> list[DocLimit]:
    return [DocLimit(rule_id=d.get("rule_id", "R1"), name=d.get("name", "velocity_band"),
                     low=d.get("low"), high=d.get("high"), unit=d.get("unit", "m/s"),
                     applies_from_nb=d.get("applies_from_nb"), applies_to_nb=d.get("applies_to_nb"),
                     file=d["file"], page=int(d["page"]), quote=d.get("quote", ""),
                     applies_to=d.get("applies_to", ""), evidence_ok=bool(d.get("evidence_ok")))
            for d in checked_limits]


def build_scenario(checked_values: list[dict], checked_shared: list[dict], changes: list[dict],
                   change_text: str, register_entries: list[dict] | None = None) -> dict:
    touched = {c.get("input") for c in changes} | ({"working"} if any(c.get("input") == "arrangement" for c in changes) else set())
    merged, disagreements, sources = merge_values(checked_values, touched)

    issued_vals = {**merged, **register_values(register_entries or [])}
    after_vals = {**issued_vals, **change_values(changes, change_text)}

    shared, shared_src = _shared(checked_shared)
    return {
        "issued": build_inputs(issued_vals, shared, shared_src),
        "after": build_inputs(after_vals, shared, shared_src),
        "after_values": after_vals,
        "disagreements": disagreements,
        "sources": sources,
        "shared_discharge": shared,
    }
