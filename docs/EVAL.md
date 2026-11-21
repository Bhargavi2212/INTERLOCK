# Evaluation

How we know Interlock works, measured against simple baselines, on inputs we did not write. Every number in the results table is produced by code written today, except the "By hand" column (a timed person). Formulas: `RULES.md`. Model jobs: `ARCHITECTURE.md`.

---

## 1. Rules for every measurement

1. **Answer key before the run.** Write the expected answer (pages, values, status) and **commit it to `eval/keys/` before running any system on that case.** The commit time is the proof the key came first.
2. **Read every match.** A script proposes matches; a person confirms each one. Keyword overlap never counts as a hit on its own.
3. **Same input, same scoring for every system.**
4. **Repeat runs:** set E runs 3 times per case for Interlock and for the one-call baseline; we report the worst run and the spread. Sets A, B and F run once.
5. **When runs happen:** the eval runner starts in the background at the start of phase 4, so phase 5 only collects results and fills the table.
6. **Raw outputs** of every run are committed to `eval/results/` as small JSON, so the evidence behind each number can be checked. The table in §5 is the only home of the results.
7. **Report failures in the table**, not in a footnote.

## 2. Test sets

| Set | What | Answer key | Role |
|---|---|---|---|
| **A. BHEL changes** | 3 changes on the BHEL Lara tender (851 pages): SG Unit-1 floor wash pumps, PT filter backwash pumps, MRS Unit-1 waste water pumps | Text search for every name **plus** every P&ID and data-sheet page of that system read by a person, committed in phase 1, before phase 2 runs | **Development set:** used while building and to set the Decisions API threshold, so not counted as unseen |
| **B. P&ID locate** | 5 items on BHEL P&ID D3-146: SG Unit-1 floor wash pumps, SG Unit-2 floor wash pumps (look-alike), MRS Unit-1 waste water pumps, transformer yard Unit-2 oily waste pumps, SG Unit-3 floor wash pumps (does not exist) | True label position from the PDF's own text layer (D3-146 has one). No model. Committed in phase 1 | Drawing accuracy |
| **D. Rules** | Every test case in `RULES.md` | Worked by hand | Math correctness |
| **E. Unseen changes** | E1-E5: changes written by a separate Claude session from the BHEL pages, which did not see Interlock's code, prompts or results; never used while building; keys confirmed by Bhargavi. E6+: changes written by people at the event, if collected. | Committed before any system runs on them (E1-E5: 21 Nov, before phase 2) | **The unseen test.** Problem Statement One's core |
| **F. Math from the documents** | 3 calculations on BHEL values (e.g. floor-wash discharge velocity against D5-200) | Input values read from the pages by a person, worked by hand, committed in phase 1, before any run | Code math vs one Gemini call's math |

**How the keys were written (disclosure).** Sets A, B and F: drafted by Claude from text search and the PDF text layer (no Gemini call), confirmed by Bhargavi. Their `written_at` was corrected from 12:55 to 12:42 (when each file was first saved) after they were committed (commit `5859356`), before any run. Set E: see the set E row; E keys confirmed by Bhargavi; author field "Claude (separate session)".

Public source: BHEL tender PE-TS-508-404-W001 (Lara STPP Stage-II water treatment packages). Local copies live in `data/bhel/` (git-ignored).

| # | File | Pages |
|---|---|---|
| 1 | `data/bhel/Part1.pdf` | 150 |
| 2 | `data/bhel/Part2.pdf` | 150 |
| 3 | `data/bhel/Part3.pdf` | 150 |
| 4 | `data/bhel/Part4.pdf` | 150 |
| 5 | `data/bhel/Part5.pdf` | 251 |
| | **Total** | **851** |

In answer keys, `file` is the name as uploaded (e.g. `Part3.pdf`) and `page` is 1-based within that file.

### Answer key format

One JSON file per case in `eval/keys/` (`A1.json`, `B1.json`, `E1.json`, `F1.json` ...):

```json
{"id": "E1", "author": "first name", "written_at": "HH:MM",
 "change": "text exactly as the author wrote it",
 "expected_pages": [{"file": "name.pdf", "page": 12}],
 "expected_values": [{"attribute": "working pumps", "value": "2", "unit": "count", "file": "name.pdf", "page": 12}],
 "documents_disagree": false,
 "expected_verdict": "BLOCK"}
```

Counts use `"unit": "count"`. `expected_verdict` is BLOCK, REVIEW or no conflicts found (`RULES.md`). Sets A and E use this format (set A: `"author": "Bhargavi"`).

**Set B** (one per item; box normalised 0-1 from the PDF text layer by `scripts/label_positions.py`, checked by a person):

```json
{"id": "B1", "item": "SG Unit-1 floor wash pumps", "file": "Part3.pdf", "page": 0,
 "label_text": "...", "found": true, "box": [0.41, 0.22, 0.47, 0.24]}
```

`page` is the page of the file where drawing D3-146 appears (the drawing number is not the page number). The absent item has `"found": false` and no `box`.

**Set F** (inputs read from the pages by a person, worked by hand):

```json
{"id": "F1", "calculation": "R1 velocity, floor-wash discharge vs D5-200",
 "inputs": [{"name": "flow_per_pump", "value": 105, "unit": "m3/h", "file": "Part4.pdf", "page": 57, "quote": "..."}],
 "expected": {"value": 3.71, "unit": "m/s", "status": "flagged"}}
```

## 3. Baselines

| Baseline | What it is |
|---|---|
| **Keyword search** | Find the change's item name as typed, on every page |
| **One Gemini call** | One Argon call with all pages and the change: "list every page about this item, its values, and whether the change is safe" |
| **One Gemini call doing the math** | The same call asked to compute the set F calculations |
| **By hand** | Bhargavi does one set-A change with a PDF reader and Ctrl-F, timed. One expert, one change, disclosed as the builder |

## 4. Metrics

| Metric | Definition |
|---|---|
| Page recall | key pages found / key pages, worst of runs |
| Wrong pages | pages returned that are not about the item |
| Value accuracy | values with correct number and unit / values in key |
| Evidence | values whose quote is on the cited page / values returned |
| Same-item check | Decisions API precision and recall at the chosen threshold, on set A candidate pages including look-alikes |
| Drawing hit | box centre within 3% of the page of the true label; "not found" for the absent item |
| Math correct | within 1% of the hand answer |
| Fix outcome | proven / refused / wrong, against the expected outcome |
| Clash caught | conflicting later changes caught from the register |
| Time | seconds from change submitted to verdict (target < 90 s) |

## 5. Results (filled during phase 5, today's code only)

The only home of these numbers. Raw outputs behind each cell: `eval/results/`.

| Metric | Keyword | One call | By hand | Interlock |
|---|---|---|---|---|
| Set E page recall (worst of 3) | | | n/a | |
| Set E wrong pages | | | n/a | |
| Set A page recall (dev set) | | | | |
| Same-item check precision / recall | n/a | n/a | n/a | Set A (dev set, threshold chosen on it): threshold **0.25**, precision 1.00 / recall 1.00 over the 19 candidate pages (10 key, 9 not); at the starting 0.5: 1.00 / 0.90 (A1 Part1 p.45, P(yes) 0.385, rejected). Key pages 0.385-0.94, non-key ≤ 0.081. Recall counts candidates only: a key page never found (A3 Part1 p.45) is a page-recall miss. Raw: `eval/results/run_2a419c376ac4.json`, `run_c4de3b150649.json`, `run_50d3d8363f83.json`. Set E: pending (threshold frozen) |
| Set B drawing hits | n/a | | n/a | |
| Set F math correct | n/a | | | |
| Fix proven / refused correctly | n/a | n/a | n/a | |
| Clash caught | n/a | n/a | n/a | |
| Time per change | | | | |

## 6. Where it still fails

Filled in honestly as results arrive. Known limits:

- **Sets over 1,048,576 tokens** are refused with a message today; only code search runs over them.
- **Drawings without a text layer** cannot be scored automatically; a person marks the right answer.
- **Values whose unit is not printed** next to them are held, not guessed.
- **Consequences** only reach items the documents connect by name or off-page arrow; anything not written down is invisible.
- **Parallel pump flow** is an upper bound (`RULES.md` R1).
- **Set E authorship:** E1-E5: changes written by a separate Claude session from the BHEL pages, which did not see Interlock's code, prompts or results; never used while building; keys confirmed by Bhargavi. E6+: changes written by people at the event, if collected. E1-E5 are therefore not changes written by people at the event; their keys were confirmed by Bhargavi.
- **Key authorship:** sets A, B and F were drafted by Claude from text search and the PDF text layer (no Gemini call) and confirmed by Bhargavi; `written_at` corrected from 12:55 to 12:42 after commit (`5859356`), before any run.
