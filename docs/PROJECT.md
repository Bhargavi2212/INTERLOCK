# Interlock

**No plant change is signed off until every document agrees, and the numbers still work.**

Built at the Gemini 4 NYC Hackathon (Cerebral Valley x Google DeepMind), 21 Nov 2026. Problem Statement One, "5 Sigma".

---

## 1. The problem

A process plant wants to change something. Example from a real tender (BHEL, Lara super thermal power project, water treatment package):

> "SG Unit-1 floor wash water transfer pumps: go from 1 working + 1 standby to 2 working + 1 standby."

Before anyone approves it, an engineer has to work through hundreds of pages of specifications, data sheets and P&ID drawings and answer three questions:

1. **Where is this equipment described, and do those pages agree today?**
2. **If we make the change, what else stops working?** (the pipe, the sump, the spare pump, the motor supply)
3. **Is there a safe way to do it?**

Today this is manual reading and hand calculation. In the builder's experience (plant analytics, Haber Solutions) a change request takes **2-4 weeks** of engineering review. That figure is experience, not a measurement; see `EVAL.md` for what we actually measure.

Errors get through. In the issued BHEL tender, the same pumps are **1W+1S** on the scope page and **2W** on the data sheet and the P&ID.

## 2. Who it is for

The engineer who has to say yes or no to a plant change: an EPC or owner's engineer handling a change request (management of change). They are accountable for the answer, so every number we show must come with where it came from.

## 3. What Interlock does

Input: the plant's documents, uploaded as **a whole folder or several individual files** (PDFs: specs, data sheets, P&IDs; other file types are listed as skipped, never silently dropped), and one change written in plain English.

1. **Finds the equipment everywhere it appears**, under all its names, with the exact sentence each value comes from. Code checks every quoted sentence is really on its page.
2. **Shows it on the real drawing**: the pump is boxed on the P&ID image, with its values beside it.
3. **Runs the engineering calculations in code**, not in the model: pipe velocity, standby, sump time, relief valve, design pressure, chemical dose (`RULES.md`). Each result is **OK**, **flagged** or **held** (an input is missing, and we say which).
4. **Gives a verdict**: **BLOCK**, **REVIEW**, or **no conflicts found in N pages checked**. There is no plain PASS: the system can miss things and says so.
5. **A Managed Agent proposes a fix**, the rules re-run on it, and it is either proven or refused, with reasons.
6. **The plant remembers**: approved changes are kept in a register. A later change that clashes with an approved one is caught by a check in our code, before any fix is asked for.

## 4. The demo case (one story, start to finish)

The BHEL floor-wash change above. Expected behaviour (rules and numbers from `RULES.md`; pages from `EVAL.md` key A1):

- **Pages found:** scope (1W+1S), data sheet (2W), P&ID (2W). The documents already disagree.
- **Velocity limit comes from the tender itself:** BHEL D5-200 limits pump discharge lines of 200 mm and above to 2.5 m/s (2.1 m/s lower value, information only).
- **The drawing decides the line:** the P&ID (drawing D3-146, `Part3.pdf` p.146) shows both pump discharges joining one 200 NB header; there is no 100 NB line on this system.
- **The change:** two pumps running into the shared 200 NB header is 1.86 m/s (an upper bound for parallel pumps): **OK**, with an information note that it is below the 2.1 m/s lower value. Velocity does not block this change. (The shared header is read from the drawing in phase 3; until then R1 is **held**: "documents do not state in text whether the pumps share one discharge line".)
- **Standby:** the data sheet as issued has 2 pumps installed. The change as written (2W+1S) needs 3 installed: 2 < 2 + 1 → **flagged**.
- **Sump:** inflow is not stated: **held**, with pump-out time shown as information.
- **Verdict: BLOCK**, from the documents that disagree (scope 1W+1S vs data sheet and P&ID 2W) and the standby check.
- **The fix:** the agent proposes a third pump (3 installed); the header is already 200 NB. The server re-runs the rules: velocity OK, standby OK, sump still held as before → **proven**.
- **The register:** after approval, a later change that removes the third pump is BLOCKed by the register check.

## 5. What we are NOT building today

- A knowledge graph, or per-page extraction of every value in the whole set (slow, and one long read finds the pages).
- A tool that hunts every error in a whole tender.
- The Decisions API as a pass/fail judge (it has a narrower, measured job).
- A dashboard. The product is the change check, the drawing and the proven fix.
- User accounts, billing, multi-tenant admin.

## 6. Success today

- Every number in the proof table (`EVAL.md`) produced by code written today, except the "By hand" column (a timed person).
- The unseen test (`EVAL.md` set E, authorship disclosed there): changes Interlock never saw while building, keys committed before any run.
- The demo case works live on the deployed product, on a change typed by a judge.
- At least one honest "where it fails" line.

## 7. Event rules we follow

- **New work only.** All code and documents written today in this repo.
- Repo public. Demo shows only what was built today.
- At least two Gemini 4 models with clear jobs, plus the Decisions API (`ARCHITECTURE.md` section 3).

## 8. Documents

| Doc | Answers |
|---|---|
| `PROJECT.md` | What and why (this file) |
| `ARCHITECTURE.md` | How it fits together |
| `RULES.md` | Is the math right |
| `EVAL.md` | How we know it works |
| `PHASES.md` | What is next, and is it done |

Each fact lives in one document. Others point to it.
