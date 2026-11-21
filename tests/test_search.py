from app.reading.search import merge_candidates, search_pages

PAGES = [
    {"n": 0, "file": "Part1.pdf", "page": 43, "text": "SG UNIT-1 FLOOR WASH WATER TRANSFER PUMPS (1W+1S)"},
    {"n": 1, "file": "Part3.pdf", "page": 146, "text": "SG UNIT-1 FLR WASH WTR TRANSFER PUMPS 200NB"},
    {"n": 2, "file": "Part4.pdf", "page": 58, "text": "ESP UNIT-2 FLOOR WASH WATER SUMP"},
    {"n": 3, "file": "Part4.pdf", "page": 99, "text": "Clarifier sludge"},
]


def test_spacing_and_hyphen_insensitive():
    hits = search_pages(PAGES, ["floorwash water", "FLR-WASH"], unit_tag="Unit-1")
    found = {(h["file"], h["page"]) for h in hits}
    assert ("Part1.pdf", 43) in found and ("Part3.pdf", 146) in found
    assert ("Part4.pdf", 99) not in found


def test_other_unit_tagged_look_alike():
    hits = {h["page"]: h for h in search_pages(PAGES, ["floor wash water"], unit_tag="Unit 1")}
    assert hits[43]["look_alike"] is False
    assert hits[58]["look_alike"] is True


def test_merge_found_by():
    s = search_pages(PAGES, ["floor wash water"])
    merged = {(c["file"], c["page"]): c for c in merge_candidates(
        s, [{"file": "Part1.pdf", "page": 43, "why": "scope"}, {"file": "Part5.pdf", "page": 200, "why": "D5-200"}])}
    assert merged[("Part1.pdf", 43)]["found_by"] == "both"
    assert merged[("Part4.pdf", 58)]["found_by"] == "search"
    assert merged[("Part5.pdf", 200)]["found_by"] == "longread"
