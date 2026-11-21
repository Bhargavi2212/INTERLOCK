"""JSON schemas for every structured output (ARCHITECTURE.md section 3: never hand-parsed JSON)."""

from app.rules.engine import INPUT_QUANTITY

INPUT_NAMES = sorted(INPUT_QUANTITY)
# A change never states the standby requirement (RULES.md R2: from the documents or the default).
CHANGE_INPUTS = [n for n in INPUT_NAMES if n != "standby_required"]
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
            "properties": {"input": {"type": "string", "enum": CHANGE_INPUTS}, "from": STR, "to": STR, "unit": STR},
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
            "properties": {"rule_id": {"type": "string", "enum": ["R1"]}, "name": STR, "low": NUM, "high": NUM, "unit": STR,
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

ONE_CALL = {
    "type": "object",
    "properties": {
        "pages": {"type": "array", "items": {"type": "object", "properties": {"file": STR, "page": INT, "why": STR},
                                             "required": ["file", "page"]}},
        "values": {"type": "array", "items": {"type": "object",
                   "properties": {"attribute": STR, "value": STR, "unit": STR, "file": STR, "page": INT, "quote": STR},
                   "required": ["attribute", "value", "file", "page", "quote"]}},
        "verdict": {"type": "string", "enum": ["BLOCK", "REVIEW", "no conflicts found"]},
        "why": STR,
    },
    "required": ["pages", "values", "verdict"],
}

AGENT_ANSWER = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string", "enum": ["proposed", "refused"]},
        "fix": {"type": "array", "items": {"type": "object",
                "properties": {"input": {"type": "string", "enum": ["line_nb", "installed"]},
                               "from": STR, "to": STR, "unit": STR, "why": STR},
                "required": ["input", "to", "unit", "why"]}},
        "tries": {"type": "array", "items": {"type": "object",
                  "properties": {"n": INT, "candidate": STR, "flagged": {"type": "array", "items": STR},
                                 "newly_held": {"type": "array", "items": STR}, "note": STR},
                  "required": ["n", "candidate", "flagged", "newly_held"]}},
        "reasons": {"type": "array", "items": STR},
        "smoke": {"type": "object", "properties": {"r1_velocity": NUM, "runs_listing": STR}},
        "bundle_sha256": STR,
    },
    "required": ["outcome", "fix", "tries", "reasons", "bundle_sha256"],
}
