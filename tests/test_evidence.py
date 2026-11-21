from app.reading.evidence import check_limit, check_value, page_texts, quote_on_page

PAGE = ("SPECIFICATION FOR PUMPS\nRated capacity, each m3/ hr.   105\n"
        "Number required   Two (2W) nos.\nEffective Capacity, m3 105 M3\n"
        "Pump discharge 50-150 mm 1.8–2.4 m/s; 200 mm and above 2.1-2.5 m/s")
TEXTS = page_texts([{"file": "Part4.pdf", "page": 57, "text": PAGE}])


def val(**kw):
    base = {"input": "flow_per_pump", "value": "105", "unit": "m3/hr", "file": "Part4.pdf", "page": 57,
            "quote": "Rated capacity, each m3/ hr. 105"}
    return {**base, **kw}


def test_exact_quote_passes_after_normalising():
    r = check_value(val(quote="Rated  capacity, each m3/ hr.\n105"), TEXTS)
    assert r["evidence_ok"], r["evidence_reason"]


def test_table_row_out_of_order_passes():
    ok, why = quote_on_page("105 Rated capacity each m3/ hr.", PAGE)
    assert ok and "table row" in why


def test_quote_not_on_page_fails():
    r = check_value(val(quote="Rated capacity, each 120 m3/hr"), TEXTS)
    assert not r["evidence_ok"] and "not on the page" in r["evidence_reason"]


def test_value_not_in_quote_fails():
    r = check_value(val(value="110"), TEXTS)
    assert not r["evidence_ok"] and "not in the quote" in r["evidence_reason"]


def test_decimal_equal_number_passes():
    assert check_value(val(value="105.0"), TEXTS)["evidence_ok"]


def test_unknown_unit_fails():
    r = check_value(val(unit="gpm"), TEXTS)
    assert not r["evidence_ok"] and "unit" in r["evidence_reason"]


def test_count_as_digits_from_words_quote():
    r = check_value({"input": "working", "value": "2", "unit": "nos.", "file": "Part4.pdf", "page": 57,
                     "quote": "Number required Two (2W) nos."}, TEXTS)
    assert r["evidence_ok"], r["evidence_reason"]


def test_wrong_page_fails():
    assert not check_value(val(page=58), TEXTS)["evidence_ok"]


def test_text_input_empty_unit_passes():
    page = page_texts([{"file": "a.pdf", "page": 1, "text": "Service: floor wash water"}])
    r = check_value({"input": "service", "value": "floor wash water", "unit": "", "file": "a.pdf", "page": 1,
                     "quote": "Service: floor wash water"}, page)
    assert r["evidence_ok"]


def test_limit_checked_with_dash_variants():
    lim = {"rule_id": "R1", "low": 1.8, "high": 2.4, "unit": "m/s", "file": "Part4.pdf", "page": 57,
           "quote": "50-150 mm 1.8-2.4 m/s"}
    assert check_limit(lim, TEXTS)["evidence_ok"]
    assert not check_limit({**lim, "high": 2.5}, TEXTS)["evidence_ok"]


def _count(value, quote, input_name="installed"):
    page = page_texts([{"file": "a.pdf", "page": 1, "text": quote}])
    return check_value({"input": input_name, "value": value, "unit": "nos.", "file": "a.pdf", "page": 1,
                        "quote": quote}, page)


def test_count_words_and_arrangement_totals():
    assert _count("2", "Number required Two (1W+1S) nos.")["evidence_ok"]      # word Two
    assert _count("3", "Three (2W+1S) nos.")["evidence_ok"]                    # word and 2+1
    assert _count("2", "Pumps (1W+1S) nos.")["evidence_ok"]                     # installed = W+S
    assert _count("1", "Number required Two (1W+1S) nos.", "working")["evidence_ok"]
    assert not _count("4", "Three (2W+1S) nos.")["evidence_ok"]


def test_number_word_value_accepted():
    assert _count("Two", "Number required Two (1W+1S) nos.")["evidence_ok"]
