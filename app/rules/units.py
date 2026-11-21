"""Unit parsing. Every factor comes from rules.yaml (`cfg` = its `units:` section);
this file holds only parsing. Unknown unit -> UnknownUnit (the engine makes it held).
"""

from __future__ import annotations

import math
import re

SUPERSCRIPTS = str.maketrans({"³": "3", "²": "2", "¹": "1"})
ABSOLUTE_WHOLE = {"bara": "bar", "kpaa": "kpa", "kpa(a)": "kpa", "psia": "psi"}
GAUGE_WHOLE = {"barg": "bar", "psig": "psi"}
QUANTITY_TABLES = {
    "flow": "flow",
    "volume": "volume",
    "concentration": "concentration",
    "density": "density",
    "velocity": "velocity",
}
INCH_UNITS = {'"', "in", "inch", "inches", "nps"}


class UnknownUnit(ValueError):
    """The unit is not in the RULES.md Units table."""


def normalise(unit: str) -> str:
    """Lower-case, superscripts to digits, no spaces or dots, 'hr' -> 'h'."""
    s = (unit or "").translate(SUPERSCRIPTS).lower()
    s = re.sub(r"[\s.]", "", s)
    return s.replace("hr", "h")


def _number(value, words: dict | None = None) -> float:
    """A number, or a number word from rules.yaml (one..twelve)."""
    if isinstance(value, bool):
        raise UnknownUnit("a yes/no value is not a number")
    if isinstance(value, str) and words and value.strip().lower() in words:
        return float(words[value.strip().lower()])
    try:
        return float(value)
    except (TypeError, ValueError):
        raise UnknownUnit(f"'{value}' is not a number") from None


ARRANGEMENT_IN_TEXT = re.compile(r"(\d+)\s*w\s*\+\s*(\d+)\s*s", re.I)


def counts_in_text(text: str, cfg: dict) -> set[float]:
    """Counts a quote states: digits, number words (one..twelve), and for each
    arrangement NW+MS also N+M (installed = working + standby)."""
    s = str(text or "").lower()
    found = {float(x) for x in re.findall(r"\d+", s)}
    words = cfg.get("number_words", {})
    found |= {float(words[w]) for w in re.findall(r"[a-z]+", s) if w in words}
    for w, sb in ARRANGEMENT_IN_TEXT.findall(s):
        found.add(float(int(w) + int(sb)))
    return found


def pressure_marking(unit: str) -> tuple[str, str | None]:
    """Return (normalised base unit, 'a' | 'g' | None).

    Absolute only by an '(a)' marker, a separate 'a' token before normalising
    ('bar a', 'kPa a'), or the whole units bara, kpaa, kpa(a), psia.
    Gauge by '(g)', a separate 'g' token, or barg, psig.
    """
    raw = (unit or "").translate(SUPERSCRIPTS).lower().strip()
    tokens = raw.split()
    whole = normalise(raw)
    if whole in ABSOLUTE_WHOLE:
        return ABSOLUTE_WHOLE[whole], "a"
    if whole in GAUGE_WHOLE:
        return GAUGE_WHOLE[whole], "g"
    marking = None
    if "(a)" in raw or (len(tokens) > 1 and tokens[-1] == "a"):
        marking = "a"
    elif "(g)" in raw or (len(tokens) > 1 and tokens[-1] == "g"):
        marking = "g"
    if len(tokens) > 1 and tokens[-1] in ("a", "g"):
        raw = " ".join(tokens[:-1])
    base = normalise(raw.replace("(a)", "").replace("(g)", ""))
    return base, marking


def strength_kind(unit: str) -> str:
    """'% w/w' -> 'w/w', '% w/v' -> 'w/v'; a % without either -> UnknownUnit."""
    s = normalise(unit)
    if not s.startswith("%"):
        raise UnknownUnit(f"strength unit '{unit}' is not a %")
    if "w/w" in s:
        return "w/w"
    if "w/v" in s:
        return "w/v"
    raise UnknownUnit(f"strength '{unit}' does not say w/w or w/v")


def to_base(quantity: str, value, unit: str, cfg: dict) -> tuple[float, list[str]]:
    """Convert to the base unit of `quantity`. Returns (number, assumptions).

    Bases: flow m3/h, pressure bar(g), head m, nb mm (nominal bore),
    diameter m, volume m3, concentration mg/L, strength fraction,
    density kg/L, velocity m/s, count.
    """
    n = _number(value, cfg.get("number_words"))
    u = normalise(unit)
    assumptions: list[str] = []

    if quantity in QUANTITY_TABLES:
        table = cfg[QUANTITY_TABLES[quantity]]
        if u not in table:
            raise UnknownUnit(f"{quantity} unit '{unit}' is not in the Units table")
        return n * table[u], assumptions

    if quantity == "pressure":
        base, marking = pressure_marking(unit)
        table = cfg["pressure"]
        if base not in table:
            raise UnknownUnit(f"pressure unit '{unit}' is not in the Units table")
        p = n * table[base]
        if marking == "a":
            p -= cfg["atm_bar"]
            assumptions.append(f"absolute pressure converted to gauge (minus {cfg['atm_bar']} bar)")
        elif marking is None:
            assumptions.append(f"pressure '{unit}' has no g/a marking; assumed gauge")
        return p, assumptions

    if quantity == "head":
        if u != "m":
            raise UnknownUnit(f"head unit '{unit}' is not m")
        return n, assumptions

    if quantity == "nb":
        if u in ("nb", "dn", "mm", "mmnb", "nbmm"):
            return n, assumptions
        if u in INCH_UNITS:
            table = cfg["nps_to_nb"]
            if n.is_integer() and int(n) in table:
                return float(table[int(n)]), assumptions
            raise UnknownUnit(f"NPS {value} inch is not in the NPS table")
        raise UnknownUnit(f"pipe size unit '{unit}' is not NB, DN or NPS inches")

    if quantity == "diameter":
        if u == "mm":
            return n * cfg["mm_to_m"], assumptions
        if u in INCH_UNITS:
            return n * cfg["inch_to_m"], assumptions
        raise UnknownUnit(f"diameter unit '{unit}' is not mm or inches")

    if quantity == "strength":
        strength_kind(unit)
        return n * cfg["percent_to_fraction"], assumptions

    if quantity == "count":
        if u not in cfg["count_units"]:
            raise UnknownUnit(f"count unit '{unit}' is not one of {cfg['count_units']}")
        if not n.is_integer() or n < 0:
            raise UnknownUnit(f"count {value} is not a whole number")
        return n, assumptions

    raise UnknownUnit(f"unknown quantity '{quantity}'")


# Searched anywhere in the printed text (lower case); the first match wins.
ARRANGEMENT = re.compile(r"(?<![a-z0-9.])(\d+)\s*w(?:\s*\+\s*(\d+)\s*s)?(?![a-z0-9])")
PERCENT_ARRANGEMENT = re.compile(r"(?<![a-z0-9.])(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*%")


def parse_arrangement(text) -> dict[str, int]:
    """Find an arrangement anywhere in the text; the first match wins.
    'Two (1W+1S) nos.' -> {'working': 1, 'standby': 1}; '(2W)' -> standby 0;
    'NXP%' (e.g. '3X100%', '2X50%') -> installed N, working ceil(100/P), standby N - working.
    None found -> UnknownUnit."""
    s = str(text).lower()
    hits = [m for m in (ARRANGEMENT.search(s), PERCENT_ARRANGEMENT.search(s)) if m]
    if not hits:
        raise UnknownUnit(f"arrangement '{text}' has no NW+MS, NW or NXP%")
    m = min(hits, key=lambda h: h.start())
    if m.re is ARRANGEMENT:
        return {"working": int(m.group(1)), "standby": int(m.group(2) or 0)}
    installed, pct = int(m.group(1)), float(m.group(2))
    working = math.ceil(100 / pct) if pct > 0 else installed + 1
    if working > installed:
        raise UnknownUnit(f"arrangement '{text}': {installed} pumps of {pct:g}% cannot cover 100%")
    return {"installed": installed, "working": working, "standby": installed - working}


def matches_phrase(text, phrases) -> str | None:
    """First phrase found in `text` as whole words, case-insensitive; else None."""
    s = " ".join(str(text or "").lower().split())
    for phrase in phrases:
        p = " ".join(str(phrase).lower().split())
        if p and re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", s):
            return phrase
    return None
