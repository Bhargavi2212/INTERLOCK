"""docs/RULES.md is the single source; rules.yaml and the tests must match it."""

import importlib
import re
from pathlib import Path

import pytest

from app.rules.engine import load_rules
from app.rules.units import normalise

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs" / "RULES.md").read_text(encoding="utf-8")
YAML = load_rules()
TOL = 1e-9

TEST_MODULES = {
    "R1": "tests.rules.test_r1_velocity",
    "R2": "tests.rules.test_r2_standby",
    "R3": "tests.rules.test_r3_sump",
    "R4": "tests.rules.test_r4_relief",
    "R5": "tests.rules.test_r5_design_pressure",
    "R6": "tests.rules.test_r6_dose",
}


def sections() -> dict[str, str]:
    parts = re.split(r"^## ", DOC, flags=re.M)
    out = {}
    for p in parts:
        m = re.match(r"(R\d+)\b", p)
        if m:
            out[m.group(1)] = p
    return out


def table_rows(text: str, after_heading: str) -> list[list[str]]:
    block = text.split(after_heading, 1)[1]
    rows = []
    started = False
    for line in block.splitlines():
        if line.startswith("|"):
            started = True
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells)
        elif started:
            break
    return rows[1:]  # drop header


def nums(cell: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", cell)]


# ---------------------------------------------------------------- ids and counts

def test_rule_ids_match():
    assert sorted(sections()) == sorted(YAML["rules"])


@pytest.mark.parametrize("rule_id", sorted(TEST_MODULES))
def test_every_doc_case_has_a_test(rule_id):
    sec = sections()[rule_id]
    after = sec.split("- **Test cases", 1)[1].splitlines()[1:]
    bullets = 0
    for line in after:
        if line.startswith("  - "):
            bullets += 1
        elif line.strip():
            break
    module = importlib.import_module(TEST_MODULES[rule_id])
    assert bullets > 0
    assert len(module.RULES_CASES) == bullets, f"{rule_id}: RULES.md has {bullets} cases"


# ---------------------------------------------------------------- confirmed values

DEFAULT_ROWS = {
    "R1 velocity max when documents state none": [("R1", "max_velocity")],
    "R1 suction velocity max when documents state none": [("R1", "max_velocity_suction")],
    "R2 standby default": [("R2", "standby_required")],
    "R3 max pump starts per hour": [("R3", "max_starts_per_hour")],
    "R4 operating / set margin": [("R4", "operating_to_set_max")],
    "R5 margin factor / adder": [("R5", "margin_factor"), ("R5", "margin_adder")],
}
LIST_ROWS = {
    "R1 solids-bearing services": ("R1", "solids_services"),
    "R5 water services (SG 1.0)": ("R5", "water_services"),
}


def confirmed_rows():
    return {r[0]: r for r in table_rows(DOC, "## Confirmed values")}


def test_confirmed_table_rows_all_known():
    assert set(confirmed_rows()) == set(DEFAULT_ROWS) | set(LIST_ROWS)


@pytest.mark.parametrize("label", sorted(DEFAULT_ROWS))
def test_default_values_match(label):
    row = confirmed_rows()[label]
    cell = row[2] if row[2] else row[1]
    expected = nums(cell)
    for (rule, key), want in zip(DEFAULT_ROWS[label], expected):
        d = YAML["rules"][rule]["defaults"][key]
        assert d["value"] == pytest.approx(want, rel=TOL), f"{label}: {key}"
        assert d["confirm"] is (not row[2]), f"{label}: confirm flag"


@pytest.mark.parametrize("label", sorted(LIST_ROWS))
def test_list_values_match(label):
    row = confirmed_rows()[label]
    cell = row[2] if row[2] else row[1]
    rule, key = LIST_ROWS[label]
    entry = YAML["rules"][rule][key]
    assert {x.strip().lower() for x in cell.split(",")} == {x.lower() for x in entry["value"]}
    assert entry["confirm"] is (not row[2])


# ---------------------------------------------------------------- units table

U = YAML["units"]
# Units-table "Unit" cell -> yaml factors it must equal
UNIT_ROWS = {
    "m3/h, m3/hr, cum/hr, cu.m/hr": [("flow", "m3/h")],
    "m3/d": [("flow", "m3/d")],
    "L/s": [("flow", "l/s")],
    "L/min": [("flow", "l/min")],
    "L/h": [("flow", "l/h")],
    "bar(g), barg": [("pressure", "bar")],
    "bar (no g/a marking)": [("pressure", "bar")],
    "kg/cm2(g)": [("pressure", "kg/cm2")],
    "kg/cm2(a)": [("pressure", "kg/cm2")],
    "kg/cm2 (no g/a marking)": [("pressure", "kg/cm2")],
    "kPa (no g/a marking)": [("pressure", "kpa")],
    "MPa (no g/a marking)": [("pressure", "mpa")],
    "psi, psig": [("pressure", "psi")],
    "m (liquid column)": [("head_m_to_bar_per_sg",)],
    "NB / DN (mm)": [("nb_to_m",)],
    "stated internal diameter in inches": [("inch_to_m",)],
    "stated internal diameter in mm": [("mm_to_m",)],
    "m3, cum": [("volume", "m3"), ("volume", "cum")],
    "mg/L, ppm": [("concentration", "mg/l"), ("concentration", "ppm")],
    "kg/L": [("density", "kg/l")],
    "m/s": [("velocity", "m/s")],
}
NO_FACTOR_ROWS = ("NPS inches", "count", "% w/w, % w/v")


def yaml_get(path):
    node = U
    for k in path:
        node = node[k]
    return node


def unit_rows():
    return table_rows(DOC, "## Units (exact factors)")


def test_every_units_row_is_checked():
    for cells in unit_rows():
        unit = cells[1]
        if unit.startswith("Absolute") or unit.startswith(NO_FACTOR_ROWS):
            continue
        assert unit in UNIT_ROWS, f"Units row '{unit}' has no yaml mapping in this test"


@pytest.mark.parametrize("unit", sorted(UNIT_ROWS))
def test_unit_factor_matches(unit):
    row = next(c for c in unit_rows() if c[1] == unit)
    to = row[2]
    m = re.search(r"(x|÷)\s*(\d+(?:\.\d+)?)", to)
    assert m, f"no factor in '{to}'"
    factor = float(m.group(2)) if m.group(1) == "x" else 1 / float(m.group(2))
    for path in UNIT_ROWS[unit]:
        assert yaml_get(path) == pytest.approx(factor, rel=TOL), f"{unit} -> {path}"


def test_flow_aliases_normalise_to_yaml_keys():
    for alias in ["m3/h", "m3/hr", "cum/hr", "cu.m/hr"]:
        assert normalise(alias) in U["flow"]


def test_count_units_match():
    row = next(c for c in unit_rows() if c[1].startswith("count"))
    listed = row[1].split("(")[0]
    doc = {normalise(x) for x in listed.split(",") if x.strip()}
    assert doc == set(U["count_units"])


def test_atmosphere_matches():
    subtracts = re.findall(r"subtract (\d+(?:\.\d+)?)", DOC)
    assert subtracts and all(float(s) == U["atm_bar"] for s in subtracts)


def test_nps_table_matches():
    row = next(c for c in unit_rows() if c[1].startswith("NPS inches"))
    pairs = {int(a): int(b) for a, b in re.findall(r'(\d+)"=(\d+)', row[2])}
    assert pairs == {int(k): v for k, v in U["nps_to_nb"].items()}


def test_percent_factor_matches():
    row = next(c for c in unit_rows() if c[1].startswith("% w/w"))
    pct, frac = re.search(r"(\d+)% → (\d+\.\d+)", row[2]).groups()
    assert U["percent_to_fraction"] == pytest.approx(float(frac) / float(pct), rel=TOL)


def test_schedule_table_matches():
    doc = {}
    for line in sections()["R1"].splitlines():
        m = re.match(r"\s*\|\s*(\d+)\s*\|\s*(\d+\.\d+)\s*\|\s*(\d+\.\d+)\s*\|", line)
        if m:
            doc[int(m.group(1))] = {"sch40": float(m.group(2)), "sch80": float(m.group(3))}
    assert doc and doc == {int(k): v for k, v in YAML["rules"]["R1"]["schedule_id_mm"].items()}
