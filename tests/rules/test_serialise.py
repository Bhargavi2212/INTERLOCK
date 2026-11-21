import json

from app.rules import run_rule
from app.rules.model import (Disputed, DocLimit, Value, doclimit_from_dict, doclimit_to_dict, result_from_dict,
                             value_from_dict, value_to_dict)
from tests.rules.conftest import bhel_bands, v


def test_value_round_trip_with_box_and_source():
    x = Value("200", "NB", file="Part3.pdf", page=146, quote="200NB", source="drawing", box=(0.1, 0.2, 0.3, 0.4))
    assert value_from_dict(json.loads(json.dumps(value_to_dict(x)))) == x


def test_disputed_round_trip():
    d = Disputed((v(1, "count", page=43), v(2, "count", page=57)))
    assert value_from_dict(json.loads(json.dumps(value_to_dict(d)))) == d


def test_doclimit_round_trip():
    dl = bhel_bands()[1]
    assert doclimit_from_dict(json.loads(json.dumps(doclimit_to_dict(dl)))) == dl


def test_rule_result_round_trip_through_json():
    r = run_rule("R1", {"flow_total": v(210, "m3/h"), "line_nb": v(200, "NB")}, bhel_bands())
    back = result_from_dict(json.loads(json.dumps(r.to_dict())))
    assert (back.rule_id, back.status, back.value, back.limit, back.notes) == (r.rule_id, r.status, r.value, r.limit, r.notes)
    assert back.inputs["line_nb"] == r.inputs["line_nb"]


def test_engine_runs_from_rules_json_without_yaml(tmp_path, monkeypatch):
    import builtins
    import yaml as _yaml
    from app.rules import engine
    data = engine.load_rules()
    j = tmp_path / "rules.json"
    j.write_text(json.dumps(data), encoding="utf-8")
    real_import = builtins.__import__

    def no_yaml(name, *a, **k):
        if name == "yaml":
            raise ImportError("no pyyaml in the sandbox")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_yaml)
    engine.load_rules.cache_clear()
    try:
        assert engine.load_rules(str(j))["rules"]["R1"]["defaults"]["max_velocity"]["value"] == 3.0
    finally:
        engine.load_rules.cache_clear()
    assert _yaml
