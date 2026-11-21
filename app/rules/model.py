"""Data the rule engine takes and returns. Plain dataclasses, no logic."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SOURCES = ("document", "drawing", "change", "fix", "register")


@dataclass(frozen=True)
class Value:
    """One input value with its evidence.

    source "document": read from a page; file, page and quote locate it, and
    evidence_ok is set by the evidence check. source "change" / "fix": from the
    change text or an agent fix; quote is that text, file "" and page 0.
    """

    value: float | int | str | bool
    unit: str
    file: str = ""
    page: int = 0
    quote: str = ""
    evidence_ok: bool = True
    source: str = "document"
    box: tuple | None = None  # drawing values: page-normalised [x0, y0, x1, y1] the code verified


@dataclass(frozen=True)
class Disputed:
    """Documents disagree about this input."""

    values: tuple[Value, ...]


@dataclass(frozen=True)
class DocLimit:
    """A design-basis limit stated in the plant's documents (e.g. a velocity band)."""

    rule_id: str
    name: str
    low: float | None
    high: float | None
    unit: str
    applies_from_nb: int | None
    applies_to_nb: int | None
    file: str
    page: int
    quote: str
    applies_to: str = ""
    evidence_ok: bool = True

    def covers_nb(self, nb: float) -> bool:
        if self.applies_from_nb is not None and nb < self.applies_from_nb:
            return False
        if self.applies_to_nb is not None and nb > self.applies_to_nb:
            return False
        return True

    def citation(self) -> str:
        return f"{self.file} p.{self.page}: '{self.quote}'"


@dataclass
class RuleResult:
    rule_id: str
    status: str  # "OK" | "flagged" | "held"
    value: float | None
    unit: str
    limit: float | None
    limit_source: str
    formula: str
    inputs: dict
    message: str
    assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---- serialisation (agent case files, stored change results) -------------------------------

def value_to_dict(v) -> dict | None:
    if v is None:
        return None
    if isinstance(v, Disputed):
        return {"disputed": [value_to_dict(x) for x in v.values]}
    d = asdict(v)
    d["box"] = list(v.box) if v.box else None
    return d


def value_from_dict(d: dict | None):
    if d is None:
        return None
    if "disputed" in d:
        return Disputed(tuple(value_from_dict(x) for x in d["disputed"]))
    fields = {k: d[k] for k in ("value", "unit", "file", "page", "quote", "evidence_ok", "source") if k in d}
    return Value(**fields, box=tuple(d["box"]) if d.get("box") else None)


def doclimit_to_dict(dl: DocLimit) -> dict:
    return asdict(dl)


def doclimit_from_dict(d: dict) -> DocLimit:
    return DocLimit(**{k: d[k] for k in DocLimit.__dataclass_fields__ if k in d})


def result_from_dict(d: dict) -> RuleResult:
    """A stored RuleResult dict back to a RuleResult (inputs restored as Values / Disputed)."""
    r = RuleResult(**{k: d[k] for k in RuleResult.__dataclass_fields__ if k in d})
    r.inputs = {k: value_from_dict(v) if isinstance(v, dict) else v for k, v in (d.get("inputs") or {}).items()}
    return r
