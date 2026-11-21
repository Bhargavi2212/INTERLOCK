# Phase 3 — build plan (for approval)

Implements `docs/specs/PHASE_3.md` **with its Amendments** (they override). No code until Bhargavi approves. Every step ends in a commit with `pytest -q` green. Claude Code never runs anything that needs the Gemini key; Bhargavi runs every live call and pastes back only printed output.

Clock: starts ~14:05. Phase window 14:15-14:45; **never cut**. Review item 6 (stronger guard tests) waits for the start of phase 4 unless Bhargavi says otherwise.

Checked before writing (not guessed):
- **Rotation bug is real:** Part3 p.146 has rotation 270; words stored by phase 2 ingest reach y = 1.408. `rect * page.rotation_matrix` puts them in 0-1.
- **Image input shape:** the installed SDK's `ImageContent` takes `{"type": "image", "data": <base64>, "mime_type": "image/png"}`: inline, the bucket stays private. Structured output goes through the v1beta client (as phase 2).
- **Calibration item exists:** "ESP UNIT-1 WASTE WATER TRANSFER PUMPS" is in Part3 p.146's text layer (two line boxes); not in set B.

---

## 0. Gates and order

| Gate | When |
|---|---|
| B keys gain `item_query` in a commit of their own | before any B run (step D1) |
| Calibration only on ESP Unit-1 (never a B item) | step D5, before `score_b.py` |
| Warm-up check on the re-ingested plant | before timing the 90 s line |

## 1. Step D1 — keys, docs, re-ingest, rotation fix → **deploy** (~12 min)

### Commit D1a `B keys: item_query added so the scorer never sees key notes`
- `eval/keys/B1-B5.json`: add `item_query` exactly as approved (A2). Nothing else in the keys changes. Alone in its commit.

### Commit D1b `phase 3: in progress; spec amendments` (already prepared)
- PHASE_3.md Amendments, PHASES.md phase 3 in progress + pointers, this plan.

### Commit D1c `phase 3: rotated-page word positions; is_drawing in pages_all; re-ingest`
- `app/ingest/ingest.py`: each word rect `* page.rotation_matrix`, normalised by `page.rect`, clamped 0-1 (same method as `scripts/label_positions.py`). `pages_all.json` entries gain `is_drawing`.
- `POST /plants/{id}/reingest` (access code): every file with status `ingested` / `failed` is set back to `uploading` and ingested again from the bucket into the same plant: pages, PNGs and `pages_all.json` rewritten from n = 0; token count kept (same text). Refused with 409 while an ingest is running.
- Tests: a PDF made in the test with `set_rotation(270)` and one known word → stored box equals the `rotation_matrix` method within 1e-4 and inside 0-1; `pages_all` has `is_drawing`; reingest keeps the plant id, rewrites pages, n starts at 0, page count unchanged.
- **Deploy** (block 6). **Bhargavi:** `POST /plants/9eeb30bca0d5/reingest` from the page (a "Re-ingest" button is added next to the plant line in this commit) and waits for "851 pages". Runs while D2-D3 are built.

## 2. Step D2 — code-only drawing pieces (~12 min, commit D2)

### `app/drawing/locate.py`
- `drawing_pages(kept, pages_all, understanding)`: kept pages with `is_drawing`, then drawing pages where code search finds any name; at most `drawing.max_pages` (2), kept first.
- `find_anchor(words, names, unit_tag, abbreviations)`: candidate lines = runs of words (same text line, gap < 1.5 word heights); a run matches if, after spaces/hyphens are removed and abbreviations applied both ways (`reading.yaml` `drawing.abbreviations`: `flr`↔`floor`, `wtr`↔`water`, `pp`↔`pump`, ...), it contains the unit tag token **and** at least two stem words of a name. Returns the label box (union of the run, plus the next line if it continues the label) and its words.
- `crop_window(anchor_box, fraction)`: window of `drawing.crop_fraction` (0.40) of page width and height centred on the anchor, clamped to the page; no anchor → whole page.
- `crop_png(page_png, window, max_px)`: crop with PyMuPDF `Pixmap` (`pymupdf.Pixmap(src, clip)` via a one-page PDF of the image), long side capped at `drawing.max_image_px` (3072).

### `app/drawing/boxes.py` (part of vision in the spec; separate so it has no model import)
- `to_page(box, fmt, crop)`: converts a model box in the calibrated format (`reading.yaml` `drawing.box_format`: order `yx` or `xy`, scale `1000` or `1`) from crop coordinates to page-normalised displayed `[x0, y0, x1, y1]`.

### `app/drawing/verify.py` (no model; the drawing evidence rule)
For each reading and the item/label boxes:
1. box inside 0-1, positive area;
2. text-layer words whose centres fall inside the box (expanded by `drawing.box_margin` 0.01) contain `label_text` (normalised, spaces ignored);
3. the value is in `label_text` (numbers as numbers; counts/arrangements via `counts_in_text`/`parse_arrangement`); unit known via `evidence.unit_known`;
4. **item box contains the anchor label's words including the unit-tag token** (A4), else `found=false` ("box does not contain the item's label");
5. `shared_discharge`: checks 1-2 on the header's size label; the topology is Argon's reading, stated as an assumption.
- Page without text layer (no words) → every reading `evidence_ok=False`, reason "not verifiable (no text layer)".
- Output: readings as value records `{input, value, unit, file, page, quote=label_text, box, source: "drawing", evidence_ok, evidence_reason}`.

### Engine / scenario / store (B5, B6, A3)
- `model.Value`: optional `box`; `SOURCES` gains `"drawing"`. `engine.Inputs._value`: evidence gate for `document` **and** `drawing`; `_cite` shows `file p.N (drawing)`.
- `scenario._doc_value`: keeps the record's `source` and `box`. **A3:** before merging, text values for `line_nb`, `line_role`, `shared_discharge` whose page is a drawing page are dropped (`is_drawing` from `pages_all`).
- Store (memory, gcp): `get_page_png`, `put_change_png`, `get_change_png` (GCS `plants/{plant_id}/changes/{change_id}/drawing.png`).
- `reading.yaml` `drawing:` max_pages 2, crop_fraction 0.40, max_image_px 3072, box_margin 0.01, box_format (placeholder until D5), abbreviations, thinking low.
- RULES.md Inputs: `drawing` source and the checks; CLAUDE.md hard rule ("…either a `quote` (text) or a `box` on a drawing whose text-layer label the code has verified"); ARCHITECTURE.md §1 step 6 and §5; PROJECT.md §4 (B9). All in this commit, with the code they describe.
- Tests (`test_drawing_locate.py`, `test_drawing_verify.py`): anchor finds "SG UNIT-1 FLR WASH WTR TRANSFER PUMPS" for names ["floor wash water transfer pump"] + "UNIT-1" and never the UNIT-2 label; crop window clamps; box conversion for each format at a crop offset (and whole-page identity); verify passes label-inside, fails label-outside, value-not-in-label, item box without the unit-tag token (look-alike), no text layer; engine holds a drawing value with `evidence_ok=False`; scenario drops a text "65NB" from a drawing page and keeps the verified drawing 50NB (A3 regression from `EVAL.md` §6).

## 3. Step D3 — vision, render, pipeline, route (~12 min, commit D3)

- `models.see(role, prompt, png, schema, thinking, usage)`: v1beta client, `input=[{"type": "text", "text": prompt}, {"type": "image", "data": base64(png), "mime_type": "image/png"}]`, structured output; same retry/logging rules (no content logged).
- `schemas.DRAWING`: `found`, `item_box`, `label_box`, `readings[{input enum [line_nb, line_role, shared_discharge, flow_per_pump, arrangement], value, unit, label_text, box, role}]`, `why`.
- `app/drawing/vision.py`: prompt per spec §3 (item, names, unit tag; box only this item; found=false if absent; label_text exactly as printed; the line these pumps discharge into, with its role); converts boxes with `boxes.to_page`; **whole-sheet fallback** (B7) when line size or shared discharge is missing and the crop was not the whole page.
- `app/drawing/render.py`: crop PNG → one-page PDF → red rectangle for the item box, thin red for verified readings with value text, grey dashed for unverified → PNG bytes.
- `pipeline.py`: step `drawing` after `same_item`, **in parallel with `values`**; verified readings merged before scenario; result `drawing{...}` per spec §5; drawing failure → step "failed: <class>" / "no drawing page", verdict unaffected; PNG stored via `put_change_png`.
- `GET /changes/{id}/drawing.png` (access code; `?full=1` → the whole page PNG).
- Tests: pipeline with fake `see` (verified shared "200NB" → R1 after 1.86 OK + note + drawing assumption; drawing failure → verdict unchanged, step says failed; no drawing page → reason in result); route needs the access code; render returns a PNG.

## 4. Step D4 — screen → **deploy** (~6 min, commit D4)

- Centre panel replaces the placeholder: the crop fetched with `X-Access-Code` and shown from a blob URL; under it, rows `value · unit · "label as printed" · verified ✓ / not verified (reason)` and `Part3.pdf p.146 (drawing)`; "view whole sheet" link (`?full=1`); "no drawing: <reason>" when absent. Calc-sheet input chips say "drawing" for drawing values.
- **Deploy.**

## 5. Step D5 — calibrate, score set B, run A1 (Bhargavi runs; ~10 min)

- `scripts/calibrate_box.py --plant <id>` (commit D5a): one vision call on the crop around **ESP UNIT-1 WASTE WATER TRANSFER PUMPS** (Part3 p.146); prints Argon's raw label box and the text-layer box, and the page-normalised result under each format (`yx/1000`, `xy/1000`, `yx/1`, `xy/1`) with its centre distance. Bhargavi pastes the output; I set `drawing.box_format` to the format with the smallest distance and record it in `vision.py`'s docstring (commit D5b). **Never a B item.**
- `scripts/score_b.py --plant <id>` (commit D5a): for each B key, understanding from **`item_query` only**; the drawing step alone on the key's page (matched by file basename); **label_box centre vs key box centre**, hit if ≤ 0.03; `found:false` keys hit if not found; writes `eval/results/b_<time>.json`; prints `B1 hit 0.004 | ... | n/5`.
- Bhargavi: warm-up check, then A1 on the live URL (red box on SG Unit-1, not Unit-2; R1 1.86 m/s OK with the note, citing the drawing's 200NB); then `score_b.py`.
- Commit raw results; misses to `EVAL.md` §6 (score to §5 in phase 5).

## 6. Done-when check

| Check | Evidence |
|---|---|
| Rotation fixed and tested; BHEL re-ingested on the live URL | test name; plant line after reingest |
| Set B scored 5/5 or misses in §6; raw in `eval/results/` | `score_b.py` table + file |
| A1 live: red box on the right pumps, readings verified, R1 uses the drawing's shared header (1.86 OK, note), drawing citation | screenshot / result JSON |
| A change with no drawing page still returns its verdict and says why | test + one live check if time allows |
| CLAUDE.md, RULES.md, ARCHITECTURE.md carry the drawing evidence rule | D2 commit |
| `pytest` green; < 90 s after one warm-up (seconds per step in the commit); `done (phase-3-drawing)`, tag, deployed | outputs |

## 7. Risks and responses

| Risk | Response |
|---|---|
| Box format differs from the assumed 0-1000 yx | calibration (D5) on ESP Unit-1 sets it; one setting |
| Anchor not found (other abbreviations) | add the abbreviation in `reading.yaml`; whole-page crop meanwhile, step says "no text-layer anchor" |
| Shared header outside the crop | whole-sheet fallback (B7) |
| Vision call slow | runs in parallel with values; seconds per step recorded |
| Argon boxes the Unit-2 look-alike | A4 check overrides to not found; shown as a miss, never silently corrected |
| Behind at 14:45 | keep D1, locate, vision, verify, red box, set B (spec §9); whole-sheet link and parallelism may wait |

## 8. Approve

Reply "approved" (or changes). I start with D1a (B keys alone).
