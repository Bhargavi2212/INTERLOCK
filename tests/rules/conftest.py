import pytest

from app.rules.engine import load_rules
from app.rules.model import DocLimit, Value

TEST_FILE = "Test.pdf"


def v(value, unit="", page=1, source="document", evidence_ok=True):
    """A Value with a test page and quote (document) or change text (change/fix)."""
    if source == "document":
        return Value(value, unit, file=TEST_FILE, page=page, quote=f"{value} {unit}".strip(),
                     evidence_ok=evidence_ok, source=source)
    return Value(value, unit, quote=f"change text: {value} {unit}".strip(), source=source)


def bhel_bands(evidence_ok=True):
    """BHEL D5-200 pump discharge velocity bands, as phase 2 would read them."""
    common = dict(rule_id="R1", name="velocity_band", unit="m/s", file="Part5.pdf", page=200,
                  applies_to="pump discharge", evidence_ok=evidence_ok)
    return [
        DocLimit(low=1.8, high=2.4, applies_from_nb=50, applies_to_nb=150,
                 quote="50-150 mm: 1.8-2.4 m/s", **common),
        DocLimit(low=2.1, high=2.5, applies_from_nb=200, applies_to_nb=None,
                 quote="200 mm and above: 2.1-2.5 m/s", **common),
    ]


@pytest.fixture
def ucfg():
    return load_rules()["units"]
