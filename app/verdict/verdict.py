"""Verdict and proven: pure functions of rule results, disagreements and clashes.

RULES.md, Verdict: any flagged result, any disagreement about a value the change
touches, or any register clash -> BLOCK; otherwise any held -> REVIEW; otherwise
"no conflicts found" (label "No conflicts found in N pages checked"). Never PASS.

disagreements: [{"attribute": str, "values": [{"file", "page", "value"}]}]
    (the caller passes only those about values the change touches)
clashes: [{"entry_id", "attribute", "approved", "proposed"}]
"""

from __future__ import annotations

BLOCK = "BLOCK"
REVIEW = "REVIEW"
NO_CONFLICTS = "no conflicts found"
VERDICTS = (BLOCK, REVIEW, NO_CONFLICTS)


def _disagreement_reason(d: dict) -> str:
    vals = "; ".join(f"{x.get('file')} p.{x.get('page')} = {x.get('value')}" for x in d.get("values", []))
    return f"documents disagree on {d.get('attribute')}: {vals}"


def _clash_reason(c: dict) -> str:
    return (f"clashes with approved change {c.get('entry_id')}: {c.get('attribute')} "
            f"approved {c.get('approved')}, proposed {c.get('proposed')}")


def verdict(results, disagreements, clashes, pages_checked: int) -> dict:
    flagged = [r for r in results if r.status == "flagged"]
    held = [r for r in results if r.status == "held"]
    reasons = [f"flagged: {r.message}" for r in flagged]
    reasons += [_disagreement_reason(d) for d in disagreements]
    reasons += [_clash_reason(c) for c in clashes]
    reasons += [f"held: {r.message}" for r in held]

    if flagged or disagreements or clashes:
        v, label = BLOCK, BLOCK
    elif held:
        v, label = REVIEW, REVIEW
    else:
        v, label = NO_CONFLICTS, f"No conflicts found in {pages_checked} pages checked"
    return {"verdict": v, "label": label, "reasons": reasons}


def proven(before, after, clashes) -> dict:
    """A proposed fix is proven when, on the fixed values: no flagged result,
    no held result for a rule that was not already held before, no clash.
    Notes never block.
    """
    held_before = {r.rule_id for r in before if r.status == "held"}
    reasons = [f"still flagged: {r.message}" for r in after if r.status == "flagged"]
    reasons += [f"newly held: {r.message}" for r in after
                if r.status == "held" and r.rule_id not in held_before]
    reasons += [_clash_reason(c) for c in clashes]
    return {"proven": not reasons, "reasons": reasons}
