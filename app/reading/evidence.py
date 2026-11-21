"""Step 5 evidence check (no model). Every value and limit read by a model must
pass all three before it reaches the rules:
  1. quote on the page (exact after normalising, or a table row whose cells
     extracted out of order: every number present and enough of its words),
  2. value in the quote (numbers compared as numbers),
  3. unit known (units.to_base accepts it, or an empty-unit input).
Failures keep the value for display, with evidence_ok False and the reason.
"""

from __future__ import annotations

import re
import unicodedata

from app.reading.settings import reading_settings
from app.rules.engine import INPUT_QUANTITY, load_rules
from app.rules.units import UnknownUnit, to_base

DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
QUOTES = {ord("‘"): "'", ord("’"): "'", ord("“"): '"', ord("”"): '"'}
NUMBER = re.compile(r"\d+(?:\.\d+)?")
WORD = re.compile(r"[a-z0-9]+")


def norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", str(text or "")).translate(DASHES).translate(QUOTES).lower()
    return " ".join(s.split())


def numbers(text: str) -> set[float]:
    return {float(x) for x in NUMBER.findall(norm(text))}


def quote_on_page(quote: str, page_text: str) -> tuple[bool, str]:
    q, t = norm(quote), norm(page_text)
    if not q:
        return False, "empty quote"
    if q in t:
        return True, "quote found on the page"
    q_nums = numbers(q)
    if q_nums and not q_nums <= numbers(t):
        return False, "quote not on the page (a number in it is not on the page)"
    words = WORD.findall(q)
    page_words = set(WORD.findall(t))
    frac = reading_settings()["evidence"]["table_row_word_fraction"]
    if words and q_nums and sum(w in page_words for w in words) / len(words) >= frac:
        return True, "table row: every number and most words found on the page"
    return False, "quote not on the page"


def value_in_quote(value, quote: str) -> bool:
    v = str(value).strip()
    if NUMBER.fullmatch(v.replace(",", "")):
        return float(v.replace(",", "")) in numbers(quote)
    return norm(v) in norm(quote) or re.sub(r"\s", "", norm(v)) in re.sub(r"\s", "", norm(quote))


def unit_known(input_name: str, value, unit: str) -> tuple[bool, str]:
    quantity = INPUT_QUANTITY.get(input_name)
    if quantity is None:
        return False, f"unknown input '{input_name}'"
    if quantity in ("text", "bool", "ratio"):
        return True, ""
    cfg = load_rules()["units"]
    candidates = ["pressure", "head"] if quantity == "pressure_or_head" else [quantity]
    for q in candidates:
        try:
            to_base(q, value, unit, cfg)
            return True, ""
        except UnknownUnit as e:
            last = str(e)
    return False, last


def page_texts(pages_all: list[dict]) -> dict[tuple[str, int], str]:
    return {(p["file"], int(p["page"])): p["text"] for p in pages_all}


def check_value(v: dict, texts: dict) -> dict:
    """v: {input, value, unit, file, page, quote}. Returns v + evidence_ok, evidence_reason."""
    out = dict(v)
    text = texts.get((v.get("file"), int(v.get("page") or 0)))
    if text is None:
        reason = f"page {v.get('file')} p.{v.get('page')} is not in this plant"
    else:
        ok, why = quote_on_page(v.get("quote", ""), text)
        if not ok:
            reason = why
        elif not value_in_quote(v.get("value"), v.get("quote", "")):
            reason = f"value '{v.get('value')}' is not in the quote"
        else:
            unit_ok, unit_why = unit_known(v.get("input", ""), v.get("value"), v.get("unit", ""))
            reason = "" if unit_ok else f"unit '{v.get('unit')}' not usable: {unit_why}"
    out["evidence_ok"] = not reason
    out["evidence_reason"] = reason or "ok"
    return out


def check_limit(lim: dict, texts: dict) -> dict:
    """A design-basis limit: quote on page, low and high in the quote, unit m/s known."""
    out = dict(lim)
    text = texts.get((lim.get("file"), int(lim.get("page") or 0)))
    reason = ""
    if text is None:
        reason = f"page {lim.get('file')} p.{lim.get('page')} is not in this plant"
    else:
        ok, why = quote_on_page(lim.get("quote", ""), text)
        if not ok:
            reason = why
        else:
            for key in ("low", "high"):
                if lim.get(key) is not None and not value_in_quote(lim[key], lim.get("quote", "")):
                    reason = f"{key} {lim[key]} is not in the quote"
                    break
            if not reason:
                try:
                    to_base("velocity", 1, lim.get("unit", ""), load_rules()["units"])
                except UnknownUnit as e:
                    reason = f"unit not usable: {e}"
    out["evidence_ok"] = not reason
    out["evidence_reason"] = reason or "ok"
    return out
