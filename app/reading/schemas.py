"""JSON schemas for every structured output (ARCHITECTURE.md section 3: never hand-parsed JSON)."""

from app.rules.engine import INPUT_QUANTITY

INPUT_NAMES = sorted(INPUT_QUANTITY)
STR = {"type": "string"}
INT = {"type": "integer"}
NUM = {"type": "number"}

UNDERSTAND = {
    "type": "object",
    "properties": {
        "item": STR,
        "names": {"type": "array", "items": STR},
        "system": STR,
        "unit_tag": STR,
        "is_pump_item": {"type": "boolean"},
        "changes": {"type": "array", "items": {
            "type": "object",
            "properties": {"input": {"type": "string", "enum": INPUT_NAMES}, "from": STR, "to": STR, "unit": STR},
            "required": ["input", "to", "unit"]}},
    },
    "required": ["item", "names", "system", "unit_tag", "is_pump_item", "changes"],
}

LONG_READ = {
    "type": "object",
    "properties": {"pages": {"type": "array", "items": {
        "type": "object", "properties": {"file": STR, "page": INT, "why": STR},
        "required": ["file", "page", "why"]}}},
    "required": ["pages"],
}

_CITE = {"file": STR, "page": INT, "quote": STR}
VALUES = {
    "type": "object",
    "properties": {
        "values": {"type": "array", "items": {
            "type": "object",
            "properties": {"input": {"type": "string", "enum": INPUT_NAMES}, "value": STR, "unit": STR, **_CITE},
            "required": ["input", "value", "unit", "file", "page", "quote"]}},
        "limits": {"type": "array", "items": {
            "type": "object",
            "properties": {"rule_id": STR, "name": STR, "low": NUM, "high": NUM, "unit": STR,
                           "applies_from_nb": INT, "applies_to_nb": INT, "applies_to": STR, **_CITE},
            "required": ["rule_id", "high", "unit", "applies_to", "file", "page", "quote"]}},
        "shared_discharge": {"type": "array", "items": {
            "type": "object", "properties": {"value": {"type": "boolean"}, **_CITE},
            "required": ["value", "file", "page", "quote"]}},
    },
    "required": ["values", "limits", "shared_discharge"],
}

EXPLAIN = {
    "type": "object",
    "properties": {"explanations": {"type": "array", "items": {
        "type": "object",
        "properties": {"attribute": STR, "likely_right_file": STR, "likely_right_page": INT,
                       "why": STR, "consequence": STR},
        "required": ["attribute", "why", "consequence"]}}},
    "required": ["explanations"],
}

HEADLINES = {
    "type": "object",
    "properties": {"headlines": {"type": "array", "items": {
        "type": "object", "properties": {"ref": STR, "headline": STR}, "required": ["ref", "headline"]}}},
    "required": ["headlines"],
}

_BOX = {"type": "array", "items": NUM}
DRAWING = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "item_box": _BOX,
        "label_box": _BOX,
        "readings": {"type": "array", "items": {
            "type": "object",
            "properties": {"input": {"type": "string",
                                     "enum": ["line_nb", "line_role", "shared_discharge", "flow_per_pump", "arrangement"]},
                           "value": STR, "unit": STR, "label_text": STR, "box": _BOX,
                           "role": {"type": "string", "enum": ["pump discharge", "discharge header", "pump suction"]}},
            "required": ["input", "value", "label_text", "box"]}},
        "why": STR,
    },
    "required": ["found", "readings", "why"],
}
