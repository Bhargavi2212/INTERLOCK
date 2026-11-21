import pytest

from app.rules.units import (
    UnknownUnit,
    matches_phrase,
    normalise,
    parse_arrangement,
    strength_kind,
    to_base,
)

ATM = 1.013


# One case per row of the RULES.md Units table: (quantity, value, unit, expected base value)
TABLE_ROWS = [
    ("flow", 10, "m3/h", 10.0),
    ("flow", 10, "m3/hr", 10.0),
    ("flow", 10, "cum/hr", 10.0),
    ("flow", 10, "cu.m/hr", 10.0),
    ("flow", 240, "m3/d", 10.0),
    ("flow", 1, "L/s", 3.6),
    ("flow", 100, "L/min", 6.0),
    ("flow", 500, "L/h", 0.5),
    ("pressure", 5, "bar(g)", 5.0),
    ("pressure", 5, "barg", 5.0),
    ("pressure", 5, "bar", 5.0),
    ("pressure", 10, "kg/cm2(g)", 9.80665),
    ("pressure", 10, "kg/cm2(a)", 9.80665 - ATM),
    ("pressure", 10, "kg/cm2", 9.80665),
    ("pressure", 500, "kPa", 5.0),
    ("pressure", 0.5, "MPa", 5.0),
    ("pressure", 100, "psi", 6.89476),
    ("pressure", 100, "psig", 6.89476),
    ("head", 50, "m", 50.0),
    ("nb", 100, "NB", 100.0),
    ("nb", 100, "DN", 100.0),
    ("nb", 4, "inch", 100.0),
    ("nb", 8, '"', 200.0),
    ("diameter", 4.026, "inch", 4.026 * 0.0254),
    ("diameter", 102.3, "mm", 0.1023),
    ("volume", 105, "m3", 105.0),
    ("volume", 105, "cum", 105.0),
    ("count", 2, "count", 2.0),
    ("count", 2, "nos.", 2.0),
    ("count", 3, "Nos", 3.0),
    ("count", 1, "No.", 1.0),
    ("count", 2, "number", 2.0),
    ("concentration", 2, "mg/L", 2.0),
    ("concentration", 2, "ppm", 2.0),
    ("strength", 10, "% w/v", 0.10),
    ("strength", 10, "% w/w", 0.10),
    ("density", 1.2, "kg/L", 1.2),
    ("velocity", 2.4, "m/s", 2.4),
]


@pytest.mark.parametrize("quantity,value,unit,expected", TABLE_ROWS)
def test_units_table_rows(ucfg, quantity, value, unit, expected):
    got, _ = to_base(quantity, value, unit, ucfg)
    assert got == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize("unit", ["m³/h", "M3 / H", "m3/hr", "Cu. M/Hr"])
def test_superscripts_spacing_case(unit):
    assert normalise(unit) in ("m3/h", "cum/h")


@pytest.mark.parametrize("unit", ["5 kPa", "kPa"])
def test_kpa_unmarked_is_gauge_with_assumption(ucfg, unit):
    got, assumptions = to_base("pressure", 5, unit.split()[-1], ucfg)
    assert got == pytest.approx(0.05)
    assert any("assumed gauge" in a for a in assumptions)


def test_mpa_unmarked_is_gauge_with_assumption(ucfg):
    got, assumptions = to_base("pressure", 0.5, "MPa", ucfg)
    assert got == pytest.approx(5.0)
    assert any("assumed gauge" in a for a in assumptions)


@pytest.mark.parametrize("value,unit,expected", [
    (200, "kPa(a)", 2.0 - ATM),
    (200, "kPa a", 2.0 - ATM),
    (200, "kpaa", 2.0 - ATM),
    (100, "psia", 6.89476 - ATM),
    (3, "bar a", 3.0 - ATM),
    (3, "bara", 3.0 - ATM),
    (3, "bar(a)", 3.0 - ATM),
])
def test_absolute_subtracts_atmosphere(ucfg, value, unit, expected):
    got, assumptions = to_base("pressure", value, unit, ucfg)
    assert got == pytest.approx(expected, rel=1e-9)
    assert any("absolute" in a for a in assumptions)


def test_gauge_marked_has_no_assumption(ucfg):
    _, assumptions = to_base("pressure", 3, "bar(g)", ucfg)
    assert assumptions == []


@pytest.mark.parametrize("quantity,unit", [
    ("flow", "gpm"),
    ("pressure", "atm"),
    ("head", "ft"),
    ("nb", "inch"),          # 5 inch is not in the NPS table (value below)
    ("volume", "litre"),
    ("count", "pcs"),
    ("strength", "%"),
    ("strength", "10"),
    ("velocity", "ft/s"),
])
def test_unknown_unit(ucfg, quantity, unit):
    with pytest.raises(UnknownUnit):
        to_base(quantity, 5, unit, ucfg)


def test_percent_without_ww_or_wv_is_unknown():
    with pytest.raises(UnknownUnit):
        strength_kind("%")
    assert strength_kind("% w/v") == "w/v"
    assert strength_kind("%w/w") == "w/w"


def test_non_number_is_unknown(ucfg):
    with pytest.raises(UnknownUnit):
        to_base("flow", "about ten", "m3/h", ucfg)


@pytest.mark.parametrize("text,expected", [
    ("1W+1S", {"working": 1, "standby": 1}),
    ("2W+1S", {"working": 2, "standby": 1}),
    ("1W+2S", {"working": 1, "standby": 2}),
    ("3W", {"working": 3, "standby": 0}),
    ("2 W + 1 S", {"working": 2, "standby": 1}),
    ("2w+1s", {"working": 2, "standby": 1}),
])
def test_arrangement(text, expected):
    assert parse_arrangement(text) == expected


@pytest.mark.parametrize("text", ["two working", "W+S", "one plus one", "200NB"])
def test_arrangement_unknown(text):
    with pytest.raises(UnknownUnit):
        parse_arrangement(text)


def test_phrase_whole_words():
    solids = ["slurry", "sludge", "ash", "waste water", "backwash"]
    assert matches_phrase("floor wash water", solids) is None      # "ash" not in "wash"
    assert matches_phrase("MRS Unit-1 Waste  Water", solids) == "waste water"
    assert matches_phrase("filter backwash", solids) == "backwash"
    assert matches_phrase("sludge water", solids) == "sludge"
    assert matches_phrase("clarified water", ["water"]) == "water"
    assert matches_phrase("", ["water"]) is None


@pytest.mark.parametrize("word,expected", [("Two", 2.0), ("three", 3.0), ("TWELVE", 12.0)])
def test_number_words_as_counts(ucfg, word, expected):
    assert to_base("count", word, "nos.", ucfg)[0] == expected


def test_counts_in_text(ucfg):
    from app.rules.units import counts_in_text
    assert counts_in_text("Number required Two (1W+1S) nos.", ucfg) >= {1.0, 2.0}
    assert 3.0 in counts_in_text("Three (2W+1S) nos.", ucfg)


@pytest.mark.parametrize("text,expected", [
    ("3X100%", {"installed": 3, "working": 1, "standby": 2}),
    ("2x50%", {"installed": 2, "working": 2, "standby": 0}),
    ("3 X 50 %", {"installed": 3, "working": 2, "standby": 1}),
])
def test_percent_arrangement(text, expected):
    assert parse_arrangement(text) == expected


@pytest.mark.parametrize("text", ["2X40%", "1X0%"])
def test_percent_arrangement_cannot_cover(text):
    with pytest.raises(UnknownUnit):
        parse_arrangement(text)


@pytest.mark.parametrize("text,expected", [
    ("Two (1W+1S) nos.", {"working": 1, "standby": 1}),
    ("Number required Two (2W) nos.", {"working": 2, "standby": 0}),
    ("(2W)", {"working": 2, "standby": 0}),
    ("2W+1S nos.", {"working": 2, "standby": 1}),
    ("Filter backwash transfer pumps (3X100%)", {"installed": 3, "working": 1, "standby": 2}),
    ("3X100% then 2W+1S", {"installed": 3, "working": 1, "standby": 2}),   # first match wins
])
def test_arrangement_found_anywhere(text, expected):
    assert parse_arrangement(text) == expected
