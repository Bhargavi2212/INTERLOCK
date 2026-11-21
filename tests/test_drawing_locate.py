import pymupdf
import pytest

from app.drawing.boxes import distance, to_page
from app.drawing.locate import crop_png, crop_window, find_anchor


def label(x, y, *lines, h=0.004, cw=0.003):
    """Words of a label printed at (x, y), one list per printed line."""
    out = []
    for i, line in enumerate(lines):
        cx = x
        for word in line.split():
            out.append([cx, y + i * h * 1.2, cx + cw * len(word), y + i * h * 1.2 + h, word])
            cx += cw * (len(word) + 1)
    return out


WORDS = (label(0.77, 0.78, "SG UNIT-1 FLR WASH WTR", "TRANSFER PUMPS")
         + label(0.90, 0.78, "SG UNIT-2 FLR WASH WTR", "TRANSFER PUMPS")
         + label(0.28, 0.76, "MRS UNIT-1 WASTE WATER", "TRANSFER PUMPS")
         + label(0.42, 0.60, "ESP UNIT-1 WASTE WATER", "TRANSFER PUMPS")
         + label(0.60, 0.70, "200NB"))


def test_anchor_unit1_not_unit2():
    a = find_anchor(WORDS, ["floor wash water transfer pump"], "UNIT-1")
    assert a["text"] == "SG UNIT-1 FLR WASH WTR TRANSFER PUMPS"
    assert a["box"][0] == pytest.approx(0.77) and a["unit_words"]


def test_anchor_look_alike_unit2():
    a = find_anchor(WORDS, ["floor wash water transfer pump"], "Unit-2")
    assert a["text"].startswith("SG UNIT-2")


def test_anchor_uses_distinguishing_name_word():
    a = find_anchor(WORDS, ["MRS Unit-1 waste water transfer pumps"], "Unit-1")
    assert a["text"].startswith("MRS UNIT-1")


def test_absent_item_has_no_anchor():
    assert find_anchor(WORDS, ["floor wash water transfer pump"], "Unit-3") is None


def test_crop_window_centred_and_clamped():
    w = crop_window([0.48, 0.48, 0.52, 0.52], 0.4)
    assert w == pytest.approx([0.3, 0.3, 0.7, 0.7])
    w = crop_window([0.95, 0.02, 0.99, 0.04], 0.4)
    assert w == pytest.approx([0.6, 0.0, 1.0, 0.4])
    assert crop_window(None) == [0.0, 0.0, 1.0, 1.0]


@pytest.mark.parametrize("fmt,box", [
    ({"order": "yx", "scale": 1000}, [250, 500, 750, 1000]),
    ({"order": "xy", "scale": 1000}, [500, 250, 1000, 750]),
    ({"order": "yx", "scale": 1}, [0.25, 0.5, 0.75, 1.0]),
])
def test_box_conversion_at_crop_offset(fmt, box):
    got = to_page(box, fmt, [0.6, 0.4, 1.0, 0.8])        # crop: x 0.6-1.0, y 0.4-0.8
    assert got == pytest.approx([0.8, 0.5, 1.0, 0.7])


def test_box_conversion_whole_page_identity():
    assert to_page([100, 200, 300, 400], {"order": "yx", "scale": 1000}, [0, 0, 1, 1]) == pytest.approx(
        [0.2, 0.1, 0.4, 0.3])
    assert distance([0, 0, 0.2, 0.2], [0, 0, 0.2, 0.2]) == 0


def test_crop_png_window_and_cap():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4000, 2000), False)
    pix.clear_with(255)
    out = crop_png(pix.tobytes("png"), [0.5, 0.5, 1.0, 1.0], max_px=1000)
    small = pymupdf.Pixmap(out)
    assert max(small.width, small.height) <= 1000 and small.width == 2 * small.height


def test_calibration_numbers_reproduce():
    """The ESP Unit-1 calibration (eval/results/calibration_esp_unit1.json): yx and xy tie on centre
    distance, IoU separates them, yx wins."""
    from app.drawing.boxes import iou
    text = [0.4214, 0.604, 0.4541, 0.6123]
    crop, raw = [0.2377, 0.4081, 0.6377, 0.8081], [489, 459, 535, 539]
    yx = to_page(raw, {"order": "yx", "scale": 1000}, crop)
    xy = to_page(raw, {"order": "xy", "scale": 1000}, crop)
    assert round(distance(yx, text), 4) == round(distance(xy, text), 4) == 0.0048
    assert round(iou(yx, text), 2) == 0.44 and round(iou(xy, text), 2) == 0.22
