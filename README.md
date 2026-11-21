# Interlock

**No plant change is signed off until every document agrees, and the numbers still work.**

An engineer types a change to a process plant ("SG Unit-1 floor wash pumps: go from 1 working + 1 standby to 2 working + 1 standby"). Interlock reads the plant's whole document set, finds every page about that equipment under all its names, boxes it on the real P&ID drawing, runs the engineering checks **in code** with every input traced to a quoted line on a page, and gives a verdict: **BLOCK**, **REVIEW**, or **no conflicts found** (never "PASS"). A **Gemini Managed Agent** then searches for a fix in the plant's own sandbox; the **server re-checks** it before anything says "proven"; the engineer approves; and the plant's **register** remembers it, so a later change that undoes it is blocked.

Built at the Gemini 4 NYC Hackathon (Cerebral Valley x Google DeepMind), 21 Nov 2026. Problem Statement One.

## Live

- **App:** https://interlock-67888742605.us-central1.run.app (one shared access code, available on request)
- **Video:** added in phase 6, recorded from the live URL at tag `phase-6-ship`
- **Test documents:** a public BHEL tender, 5 PDFs, 851 pages (listed in [`docs/EVAL.md`](docs/EVAL.md) §2)

## The demo in five steps

1. **Upload** the plant's documents as a folder or as files (PDFs; anything else is listed as skipped, never silently dropped).
2. **Type the change.** Interlock finds the scope page (1W+1S), the data sheet (2W) and the P&ID (2W): the issued documents already disagree.
3. **See the evidence:** every value with its file, page and exact quote (checked by code to be on that page); the pump boxed in red on the P&ID crop, its labels verified against the drawing's own text layer; a calc sheet with each rule's formula, limit, limit source (the tender's own velocity table) and assumptions.
4. **Verdict: BLOCK.** The standby check fails: "This change needs 3 pumps installed; the documents show 2."
5. **Find a fix.** The Managed Agent tries candidates with the real rule engine in its sandbox and proposes a third pump; the server re-runs every rule and the register check itself and stamps it **Proven by the server**. The engineer ticks each document disagreement as resolved and approves. A later change, "remove the third pump", is **BLOCKed by the register**.

## How Gemini is used

| Model | Job |
|---|---|
| Gemini 4 **Neon** | Understands the change (item, names, unit tag, changed values); the Managed Agent's model |
| Gemini 4 **Argon** | One long read over all 851 pages (automatic cache); pulls values with exact quotes; reads the P&ID image and boxes the item |
| Gemini 4 **Carbon** | When documents disagree: which page is likely right, and what goes wrong in the plant |
| Gemini 4 **Hydrogen** | One-line headlines per finding |
| **Decisions API** | "Is this page about the same item?" with a probability; threshold set once on the development set and frozen |
| **Managed Agent** (Antigravity, Neon) | One persistent sandbox per plant with the rule engine mounted; tries levers (line size, added pumps), at most 8 tries, proposes or refuses |

Details and why each model: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §3.

## Why the answer can be trusted

- **The model never decides.** Every rule (pipe velocity, standby, sump cycle; relief valve, design pressure and dose built and tested) runs in code from [`app/rules/rules.yaml`](app/rules/rules.yaml), which a test keeps identical to [`docs/RULES.md`](docs/RULES.md).
- **Every value carries its evidence.** A value reaches the rules only if code finds its quote on the cited page; a drawing value only if its box holds the printed label in the PDF's text layer and that label is nearest to this item's own label.
- **Unknown means held.** A missing value, unknown unit or unverifiable reading makes the rule **held** (named), never guessed.
- **The agent proposes; the server proves.** The server rebuilds the case from stored evidence, overlays the fix and re-runs every rule and the register check on its own code. The agent's tries are shown as the agent's report.
- **The engineer stays in charge** of document disagreements: approval needs an explicit tick for each one.

## Results, honestly

Measured on unseen changes (set E), a development set, P&ID locating and hand-worked math, against a keyword search and **one Gemini call given all pages**: [`docs/EVAL.md`](docs/EVAL.md) §5. Every failure we found is in §6.

In short: on unseen changes, one Gemini call finds about the same pages and gets more verdicts right than Interlock today. What one call cannot give is what Interlock is for: quotes checked on their page, the math done in code with its source, the verified P&ID box, a fix proven by the server, and a register that remembers. The numbers live only in `EVAL.md`.

## Run it

Windows PowerShell, from the repo root. Python 3.13 (python.org).

```powershell
conda deactivate                      # only if a conda env is active
py -3.13 -m venv .venv                # once
.venv\Scripts\activate
pip install -r requirements.txt
pytest -q                             # tests (no network, no key)
uvicorn app.api.main:app --reload --env-file .env   # local, http://127.0.0.1:8000
```

Copy `.env.example` to `.env` and fill it in yourself; it is git-ignored. Check every model answers: `python scripts/check_models.py`. Deploy (Cloud Run, Firestore, Cloud Storage, Secret Manager): [`deploy/COMMANDS.md`](deploy/COMMANDS.md).

## Repo map

| Path | What |
|---|---|
| `app/rules/` | The rule engine and units (no model, ever) |
| `app/reading/` | Change understanding, long read, same-item check, values, evidence check, scenario, pipeline |
| `app/drawing/` | P&ID: text-layer anchor, crop, Argon boxes, code verification, red box |
| `app/agent/` | Managed Agent: bundle, levers, sandbox run, server re-check |
| `app/register/` | Approve into the register; clash check |
| `app/verdict/` | Verdict and "proven" (pure functions) |
| `web/` | The one screen |
| `eval/` | Answer keys (committed before any run), baselines, raw run outputs |
| `docs/` | Project, architecture, rules, evaluation, phases, specs |

## Built today

All code and documents in this repo were written during the event on 21 Nov 2026; the commit history shows the order (docs first, answer keys before any run). Third-party libraries are listed below. The public BHEL documents used for testing are not in the repo (`data/` is git-ignored); they are listed in [`docs/EVAL.md`](docs/EVAL.md) §2.

## Libraries

Pinned in `requirements.txt`.

| Library | Used for |
|---|---|
| fastapi | HTTP API |
| uvicorn[standard] | Server |
| google-genai | Gemini models, Decisions API, Managed Agent |
| google-cloud-firestore | Plants, changes, register, jobs |
| google-cloud-storage | Uploaded PDFs, page text and images |
| google-auth | Signing upload URLs with the service account (no key file) |
| pyyaml | `rules.yaml` |
| pymupdf | PDF text, page images, text positions, drawing crops |
| python-dotenv | Loads `.env` for local scripts |
| pytest, httpx | Tests |

More: what and why [`docs/PROJECT.md`](docs/PROJECT.md) · build plan [`docs/PHASES.md`](docs/PHASES.md).
