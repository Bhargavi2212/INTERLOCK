"""Choose the drawing page(s), find the item's printed label in the text layer, crop (no model).

Words are the page's text-layer words, page-normalised in the displayed frame:
[x0, y0, x1, y1, text]. Abbreviations and stop words come from reading.yaml.
"""

from __future__ import annotations

import re

import pymupdf

from app.reading.search import squash
from app.reading.settings import reading_settings

TOKEN = re.compile(r"[a-z0-9]+")


def _cfg() -> dict:
    return reading_settings()["drawing"]


def tokens(text: str) -> list[str]:
    """Lower-case tokens with P&ID abbreviations expanded (FLR -> floor, PUMPS -> pump)."""
    abbr = _cfg()["abbreviations"]
    return [abbr.get(t, t) for t in TOKEN.findall(str(text).lower().replace("-", " "))]


def unit_pattern(unit_tag: str) -> re.Pattern | None:
    toks = TOKEN.findall(str(unit_tag or "").lower().replace("-", " "))
    if not toks:
        return None
    return re.compile(r"(?<![a-z0-9])" + r"\s*".join(map(re.escape, toks)) + r"(?![a-z0-9])")


def name_words(names: list[str]) -> list[set[str]]:
    stop = set(_cfg()["stop_words"])
    out = []
    for n in names:
        ws = {t for t in tokens(n) if t not in stop and not t.isdigit()}
        if ws:
            out.append(ws)
    return out


def segments(words: list) -> list[list]:
    """Words grouped into printed text runs: same line, no wide horizontal gap."""
    ws = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list] = []
    for w in ws:
        h = max(w[3] - w[1], 1e-6)
        yc = (w[1] + w[3]) / 2
        if lines and abs(yc - (lines[-1][0][1] + lines[-1][0][3]) / 2) <= h * 0.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    segs = []
    for line in lines:
        line.sort(key=lambda w: w[0])
        cur = [line[0]]
        for w in line[1:]:
            h = max(w[3] - w[1], 1e-6)
            if w[0] - cur[-1][2] > 2.5 * h:
                segs.append(cur)
                cur = [w]
            else:
                cur.append(w)
        segs.append(cur)
    return segs


def _below(a: list, b: list) -> bool:
    """b is the next printed line of the same label as a (under it, overlapping in x)."""
    ah = max(w[3] for w in a) - min(w[1] for w in a)
    gap = min(w[1] for w in b) - max(w[3] for w in a)
    ax0, ax1 = min(w[0] for w in a), max(w[2] for w in a)
    bx0, bx1 = min(w[0] for w in b), max(w[2] for w in b)
    return 0 <= gap <= 1.5 * ah and min(ax1, bx1) - max(ax0, bx0) > 0


def box_of(ws: list) -> list[float]:
    return [min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws)]


def find_anchor(words: list, names: list[str], unit_tag: str) -> dict | None:
    """The item's printed label: a text run (optionally with the line below it) that holds
    the unit-tag token and at least min_name_words words of one of the names."""
    pattern = unit_pattern(unit_tag)
    wanted = name_words(names)
    need = _cfg()["min_name_words"]
    segs = segments(words)
    best = None
    for i, seg in enumerate(segs):
        groups = [seg] + [seg + nxt for nxt in segs[i + 1:i + 40] if _below(seg, nxt)]
        for g in groups:
            text = " ".join(w[4] for w in g)
            low = " ".join(TOKEN.findall(text.lower().replace("-", " ")))
            if pattern is not None and not pattern.search(low):
                continue
            have = set(tokens(text))
            score = max((len(n & have) for n in wanted), default=0)
            if score >= need and (best is None or score > best["score"]):
                unit_words = [w for w in g if pattern is not None and pattern.search(
                    " ".join(TOKEN.findall(w[4].lower().replace("-", " "))))]
                best = {"box": box_of(g), "words": g, "text": text, "score": score, "unit_words": unit_words}
    return best


def drawing_pages(kept: list[dict], pages_all: list[dict], names: list[str]) -> list[dict]:
    by_key = {(p["file"], p["page"]): p for p in pages_all}
    out = [by_key[(c["file"], c["page"])] for c in kept
           if (c["file"], c["page"]) in by_key and by_key[(c["file"], c["page"])].get("is_drawing")]
    terms = [squash(n) for n in names if squash(n)]
    for p in pages_all:
        if p.get("is_drawing") and p not in out and any(t in squash(p["text"]) for t in terms):
            out.append(p)
    return out[: _cfg()["max_pages"]]


def crop_window(anchor_box: list[float] | None, fraction: float | None = None) -> list[float]:
    """Window [x0, y0, x1, y1] (page-normalised) centred on the anchor; whole page if none."""
    if anchor_box is None:
        return [0.0, 0.0, 1.0, 1.0]
    f = _cfg()["crop_fraction"] if fraction is None else fraction
    cx, cy = (anchor_box[0] + anchor_box[2]) / 2, (anchor_box[1] + anchor_box[3]) / 2
    x0 = min(max(cx - f / 2, 0.0), 1.0 - f)
    y0 = min(max(cy - f / 2, 0.0), 1.0 - f)
    return [x0, y0, x0 + f, y0 + f]


def crop_png(page_png: bytes, window: list[float], max_px: int | None = None) -> bytes:
    """Crop the stored page PNG to the window, long side capped at max_image_px."""
    max_px = max_px or _cfg()["max_image_px"]
    with pymupdf.open(stream=page_png, filetype="png") as doc:
        page = doc[0]
        w, h = page.rect.width, page.rect.height
        clip = pymupdf.Rect(window[0] * w, window[1] * h, window[2] * w, window[3] * h)
        scale = min(1.0, max_px / max(clip.width, clip.height))
        return page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(scale, scale)).tobytes("png")
