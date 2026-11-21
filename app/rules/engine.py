"""Rule engine: loads rules.yaml once and runs R1-R6. Never calls a model.

Input gate (before a rule uses an input): missing (None), a document value whose
evidence check failed, a Disputed value, an unknown unit, or a number with an
empty unit -> HeldInput -> the rule is held and the message names the input.
Nothing is ever guessed: defaults exist only for limits in rules.yaml.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from app.rules.model import Disputed, DocLimit, RuleResult, Value
from app.rules.units import UnknownUnit, to_base

RULES_PATH = Path(__file__).with_name("rules.yaml")

# Input name -> quantity (see units.to_base). "text" / "bool" may have an empty unit.
INPUT_QUANTITY = {
    "flow_total": "flow", "flow_per_pump": "flow", "pumps_into_line": "count",
    "line_nb": "nb", "line_id": "diameter", "schedule": "text", "service": "text",
    "line_role": "text",
    "installed": "count", "working": "count", "standby_required": "count",
    "arrangement": "text",
    "volume": "volume", "q_out": "flow", "q_in": "flow", "volume_is_total": "bool",
    "operating": "pressure", "set": "pressure", "design": "pressure",
    "max_suction": "pressure", "shutoff_head": "pressure_or_head", "sg": "ratio",
    "dose": "concentration", "flow": "flow", "strength": "strength",
    "density": "density", "pump_min": "flow", "pump_max": "flow",
}


# Physical quantities that must be > 0 (else held, naming the input). Gauge pressure
# (0 bar(g) and vacuum are real) and counts (0 standby is real) are not in this set.
POSITIVE_QUANTITIES = {"flow", "nb", "diameter", "volume", "concentration", "strength", "density",
                       "velocity", "head"}


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> dict:
    """rules.yaml (the source, mirrors RULES.md) or rules.json (the same data, built for the agent's
    sandbox, which has no pyyaml). With no path: rules.yaml if present, else rules.json beside it."""
    p = Path(path) if path else (RULES_PATH if RULES_PATH.exists() else RULES_PATH.with_suffix(".json"))
    with open(p, encoding="utf-8") as f:
        if p.suffix == ".json":
            return json.load(f)
        import yaml  # only where rules.yaml is read (the server); the sandbox reads JSON

        return yaml.safe_load(f)


class HeldInput(Exception):
    """A required input is missing or unusable; the rule is held."""

    def __init__(self, name: str, reason: str, notes: list[str] | None = None):
        super().__init__(f"{name}: {reason}")
        self.name = name
        self.reason = reason
        self.notes = notes or []


def _cite(v: Value) -> str:
    if v.source == "document":
        return f"{v.file} p.{v.page}"
    if v.source == "drawing":
        return f"{v.file} p.{v.page} (drawing)"
    return f"{v.source} text"


class Inputs:
    """Gatekeeper for one rule's inputs."""

    def __init__(self, raw: dict, units_cfg: dict):
        self.raw = raw or {}
        self.cfg = units_cfg
        self.assumptions: list[str] = []
        self.used: dict[str, Value] = {}

    def has(self, name: str) -> bool:
        return self.raw.get(name) is not None

    def _value(self, name: str) -> Value:
        v = self.raw.get(name)
        if v is None:
            raise HeldInput(name, "missing")
        if isinstance(v, Disputed):
            listed = "; ".join(f"{_cite(x)} = {x.value} {x.unit}".strip() for x in v.values)
            raise HeldInput(name, f"documents disagree ({listed})")
        if v.source in ("document", "drawing") and not v.evidence_ok:
            raise HeldInput(name, f"evidence check failed ({_cite(v)})")
        self.used[name] = v
        return v

    def text(self, name: str) -> str:
        return str(self._value(name).value).strip()

    def flag(self, name: str) -> bool:
        val = self._value(name).value
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ("true", "yes", "y", "1")

    def num(self, name: str, quantity: str | None = None) -> float:
        v = self._value(name)
        quantity = quantity or INPUT_QUANTITY[name]
        if quantity == "ratio":
            try:
                number = float(v.value)
            except (TypeError, ValueError):
                raise HeldInput(name, f"'{v.value}' is not a number") from None
            if number <= 0:
                raise HeldInput(name, f"must be > 0 (got {number:g})")
            return number
        if not str(v.unit or "").strip():
            raise HeldInput(name, "a number with no unit")
        try:
            number, assumptions = to_base(quantity, v.value, v.unit, self.cfg)
        except UnknownUnit as e:
            raise HeldInput(name, f"unit '{v.unit}' not usable ({e})") from None
        if quantity in POSITIVE_QUANTITIES and number <= 0:
            raise HeldInput(name, f"must be > 0 (got {number:g} {v.unit})")
        self.assumptions.extend(f"{name}: {a}" for a in assumptions)
        return number

    def pages(self) -> str:
        cites = sorted({_cite(v) for v in self.used.values()})
        return ", ".join(cites) if cites else "no inputs"


def default_limit(rule_cfg: dict, key: str) -> tuple[float, str]:
    d = rule_cfg["defaults"][key]
    state = "CONFIRM pending" if d.get("confirm") else "confirmed"
    return d["value"], f"default (RULES.md, {state})"


def run_rule(rule_id: str, inputs: dict, doc_limits=()) -> RuleResult:
    from app.rules import checks

    rules = load_rules()
    rule_cfg = rules["rules"][rule_id]
    fn = checks.CHECKS[rule_id]
    ins = Inputs(inputs, rules["units"])
    try:
        result = fn(ins, rule_cfg, rules, [d for d in doc_limits if isinstance(d, DocLimit)])
    except HeldInput as e:
        result = RuleResult(
            rule_id=rule_id, status="held", value=None, unit="", limit=None,
            limit_source="", formula=checks.FORMULAS[rule_id], inputs={},
            message=f"{rule_id} {rule_cfg['name']} held: {e.name} {e.reason}",
            notes=list(e.notes),
        )
    result.inputs = dict(inputs or {})
    result.assumptions = ins.assumptions + result.assumptions
    return result


def run_rules(inputs_by_rule: dict, doc_limits=(), live_only: bool = True) -> list[RuleResult]:
    """Run each rule present in inputs_by_rule (only live ones when live_only).

    Which rules apply to a change is decided by the caller (phase 2); a rule the
    caller includes with missing inputs comes back held.
    """
    rules = load_rules()["rules"]
    out = []
    for rule_id, cfg in rules.items():
        if rule_id not in inputs_by_rule:
            continue
        if live_only and not cfg.get("live"):
            continue
        out.append(run_rule(rule_id, inputs_by_rule[rule_id], doc_limits))
    return out
