# Phase 3 spec — Drawing

**The Amendments section at the end overrides the text above it.**

Owner docs: `PHASES.md` (phase 3; never cut), `ARCHITECTURE.md` §1 step 6, §3 (Argon reads the P&ID image), §5 (drawing.png), `CLAUDE.md` (evidence rule), `RULES.md` (Inputs), `EVAL.md` §2 set B, §4 "Drawing hit". Builds on the phase 2 code as of `869c349` and PHASE_2 Amendment **A1** (drawing evidence). Time: 14:15-14:45 (starts earlier if phase 2 closes early).

## Goal

For a change, Interlock finds the item's P&ID page, **Argon looks at the drawing image** and boxes the item, and reads from the drawing what text cannot give (the discharge line size, whether the pumps share one header). **Code** checks every box against the PDF's own text layer before anything reaches the rules. The screen shows the real P&ID crop with a red box and the values beside it. For the demo: R1 on SG Unit-1 floor wash goes from **held** (phase 2) to **1.86 m/s OK, below the documents' lower value** with the shared 200NB header cited as drawing evidence.

## 0. Bug to fix first: word positions on rotated pages [found reading `ingest.py`]

`page_record` divides `page.get_text("words")` coordinates by `page.rect`. On a rotated page (Part3 p.146 has rotation 270) the words are in the **unrotated** frame while `page.rect` and the PNG are in the **displayed** frame, so stored words are wrong (y values up to ~1.4). `scripts/label_positions.py` already does it right (`rect * page.rotation_matrix`).
- Fix: transform each word rect by `page.rotation_matrix` before normalising by `page.rect`; clamp to 0-1.
- `pages_all.json` gains `is_drawing` per page (the drawing step needs it without 851 reads).
- Test: a PDF made in the test with `page.set_rotation(270)` and one known word → normalised box matches `label_positions.py`'s method within 1e-4.
- **Bhargavi re-uploads BHEL as a new plant after this deploy** (3.5 min; old plants keep wrong words).

## 1. Files

```
app/drawing/
├── __init__.py
├── locate.py      choose drawing pages; text-layer anchor; crop window
├── vision.py      Argon call on the crop image (via models.py); schema; box conversion
├── verify.py      code check of every box against the text layer (no model)
└── render.py      red box + values drawn on the crop (PyMuPDF only); PNG bytes
app/reading/models.py   + see(role, prompt, png_bytes, schema, thinking): image + text input
app/reading/schemas.py  + DRAWING
app/reading/pipeline.py + step "drawing" after "same_item", before "values"
app/reading/reading.yaml + drawing: {...}
app/api/main.py         + GET /changes/{id}/drawing.png (access code)
web/                     centre panel: the drawing
scripts/score_b.py      set B scoring (Bhargavi runs; needs key)
tests/test_drawing_*.py
```
No new library: crops and drawing use PyMuPDF (`pymupdf.open(stream=png, filetype="png")`, `Pixmap`, `Page.draw_rect` / `insert_text` on a one-page PDF made from the image, then `get_pixmap`). If that proves awkward, Pillow may be added (pinned, README "Libraries").

## 2. Choose the drawing page(s) (`locate.py`, no model)

1. Candidates: kept pages (after same-item) with `is_drawing`, plus drawing pages where code search finds any of the understanding's `names` (spaces/hyphens ignored). At most `drawing.max_pages` (2), kept pages first.
2. **Text-layer anchor:** on the page's (fixed) `words`, find the item's label: a run of words matching any name **and** the `unit_tag` (e.g. "UNIT-1"), spaces/hyphens ignored, allowing the P&ID abbreviations seen in BHEL ("FLR WASH WTR" for floor wash water) by matching on word stems from the names (`floor`/`flr`, `wash`, `water`/`wtr`, `transfer`, `pump`). The abbreviation map lives in `reading.yaml` (`drawing.abbreviations`), not Python.
3. **Crop window:** if an anchor is found, a window of `drawing.crop_fraction` (0.30 of page width and height) centred on the anchor, clamped to the page. If none, the whole page (downscaled) and the step says "no text-layer anchor".
4. Render the crop from the stored page PNG at its full resolution (150 dpi), capped to `drawing.max_image_px` (3072) on the long side.

## 3. Argon looks (`vision.py`, via `models.see`)

- `models.see()` sends the text prompt and the PNG as an inline image part (no public URL; never make the bucket public). Use the part shape the installed SDK accepts for `interactions.create` input; check it in the SDK as was done for structured output, and record it in the module docstring.
- Thinking `low` first (`reading.yaml`), structured output, schema `DRAWING`:
```
{"found": true,
 "item_box": [ymin, xmin, ymax, xmax],          // pumps + their label, ints 0-1000 in the image (Gemini's native box format)
 "label_box": [ymin, xmin, ymax, xmax],         // the printed label text only
 "readings": [
   {"input": "line_nb", "value": "200", "unit": "NB", "label_text": "200NB",
    "box": [...], "role": "discharge header" | "pump discharge" | "pump suction"},
   {"input": "shared_discharge", "value": true, "label_text": "200NB",
    "box": [...]},                               // box covers where the discharges join AND the header's size label
   {"input": "flow_per_pump", "value": "105", "unit": "m3/h", "label_text": "105M3/HR (2W)", "box": [...]},
   {"input": "arrangement", "value": "2W", "unit": "", "label_text": "105M3/HR (2W)", "box": [...]}],
 "why": "one sentence"}
```
- Prompt: the item and its names and unit tag; "box only this item, not a similar item for another unit"; "if this item is not on the image, found=false and no boxes"; "label_text is copied exactly as printed on the drawing"; "line size: the line these pumps discharge into, with its role".
- Convert boxes from crop 0-1000 `[ymin, xmin, ymax, xmax]` to **page-normalised displayed frame** `[x0, y0, x1, y1]` 0-1 (same frame as the PNG, the fixed `words`, and set B keys).

## 4. Code checks every box (`verify.py`, no model) — the drawing evidence rule

A drawing value reaches the rules only if all pass:
1. **On the page:** box inside 0-1 with positive area.
2. **The label is really there:** the text-layer words whose centres fall inside the box (expanded by `drawing.box_margin`, 0.01 of the page) contain `label_text` (normalised, spaces ignored).
3. **The value is in the label:** the value appears in `label_text` (numbers as numbers; counts and arrangements as in `evidence.py`); unit known as in `evidence.py`.
4. **Item box:** contains at least one word of the anchor label; if the page has a text layer and the item box contains no item-name word → `found` is overridden to **false** ("box does not contain the item's label"). This is what stops a confident wrong box (set B5, the look-alike B2).
5. `shared_discharge` passes checks 1-2 (the header's size label is inside its box). The topology itself is Argon's reading of the picture; the result says so as an assumption ("pumps share one header: read from the drawing by Argon; header label '200NB' verified in the text layer at Part3 p.146") and the crop is shown for the engineer to see.
- **No text layer** on the page → boxes are shown, marked "not verifiable (no text layer)", and **no drawing value reaches the rules** (held stays held). Never guessed.
- Each checked reading becomes a value record like phase 2's, with `source: "drawing"`, `file`, `page`, `box`, `quote` = `label_text`, `evidence_ok`, `evidence_reason`. `scenario.py` accepts `source "drawing"` values like document values; RULES.md Inputs and `model.SOURCES` gain `"drawing"`.

**Doc changes in the same commit** (owner docs): `CLAUDE.md` hard rule → "Every value read from a document carries `file`, `page`, `unit` and either a `quote` (text) or a `box` on a drawing whose text-layer label the code has verified." `RULES.md` Inputs gains the drawing source and the four checks above. `ARCHITECTURE.md` §1 step 6 and §5 updated.

## 5. Into the change check (`pipeline.py`)

- New step `drawing` after `same_item`, run **in parallel with `values`** (both need only the kept pages), so the 90 s budget holds (today ~55-64 s; vision on one crop should add < 20 s in parallel).
- Its checked readings are merged with the text values before `scenario` (same merge rules: same value from text and drawing → one value citing both; different → Disputed, and a disagreement if the change touches it). `shared_discharge` from the drawing feeds `pumps_into_line` exactly as a checked text value would.
- Result gains:
```
"drawing": {"file", "page", "found", "anchor": "text layer" | "none",
            "item_box", "label_box", "crop_box",          // page-normalised 0-1, displayed frame
            "readings": [... with evidence_ok, evidence_reason ...],
            "verified": true | false, "why", "image": "drawing.png"}
```
- `render.py` draws on the crop: red box for `item_box`, thin red outline for each verified reading with its value as text beside it, grey dashed for unverified; saves GCS `plants/{plant_id}/changes/{change_id}/drawing.png` (ARCHITECTURE §5).
- Drawing failure (model error, no page) never fails the change: step state "failed: <class>" or "no drawing page", result `drawing.found=false` with the reason; the verdict is computed as before.

## 6. API and screen

- `GET /changes/{id}/drawing.png` with the access code. `<img>` cannot send headers, so `app.js` fetches it with `X-Access-Code` and shows it from a blob URL.
- The screen's centre panel (replaces the placeholder): the crop with the red box; under it the drawing readings as rows `value · unit · "label as printed" · verified ✓ / not verified (reason)` and the citation `Part3.pdf p.146 (drawing)`; a "view whole sheet" link opening the full page PNG (same route with `?full=1`). Calc sheet input chips for drawing values say "drawing".

## 7. Set B scoring (`scripts/score_b.py`)

- For each `eval/keys/B*.json`: the drawing step alone on the key's page, with the understanding built from the key's `item` text (one Neon call, as the product does). Output per key: found, predicted item box centre, key box centre, distance as a fraction of the page, **hit** if within 0.03 (EVAL.md §4) or, for `found: false` keys, hit if predicted not found.
- Files in keys are named `Part3.pdf`; plants store `bhel/Part3.pdf` (folder upload). Compare by **basename**.
- Writes `eval/results/b_<time>.json` (raw, committed). Prints `B1 hit 0.004 | ... | 5/5`. Score goes to EVAL.md §5 in phase 5; misses to §6 now.
- Bhargavi runs it (needs the key): `python scripts/score_b.py --plant <id>`.

## 8. Tests (no network; memory store; fake models)

- Rotation fix (§0).
- Box conversion: crop 0-1000 `[ymin,xmin,ymax,xmax]` → page 0-1 `[x0,y0,x1,y1]` for a crop at an offset; full page identity.
- `verify.py`: label inside box passes; label outside fails; value not in label fails; item box without the item's words → found false; no text layer → not verifiable, nothing passed on.
- Anchor: "SG UNIT-1 FLR WASH WTR TRANSFER PUMPS" found for names ["floor wash water transfer pump"] + unit tag "UNIT-1"; the UNIT-2 label is not chosen.
- Pipeline with fakes: drawing reading `shared_discharge` true with a verified "200NB" box → R1 after = 1.86 OK with the information note and the drawing assumption; drawing failure → verdict unchanged, step says failed.
- Route: drawing.png needs the access code.

## 9. Build order (30 minutes; never cut)

1. §0 fix + `is_drawing` in `pages_all` → deploy → Bhargavi re-uploads (runs during 2-3).
2. `locate.py`, `verify.py`, box conversion, tests (no model).
3. `models.see`, `vision.py`, pipeline step, `render.py`, route.
4. Centre panel. Deploy. `score_b.py`; Bhargavi runs A1 on the live URL and set B.

**If behind:** keep §0, `locate`, `vision`, `verify`, the red box and set B. The "view whole sheet" link and parallelism with `values` may wait for phase 6. A failure of vision may **not** be replaced by drawing the text-layer box alone and calling it Argon's: if Argon fails, the screen says so.

## 10. Bhargavi does herself

1. After deploy 1 of this phase: re-upload `data\bhel` as a folder, new plant; note the plant id.
2. Run A1 on the live URL: check the red box is on SG Unit-1 floor wash pumps (not Unit-2), and that R1 now cites the 200NB header from the drawing.
3. Run `python scripts/score_b.py --plant <id>`; paste the table.

## Out of scope

Drawings without a text layer verified by other means; reading lines/arrows by code; more than 2 drawing pages per change; the agent and register writes (phase 4).

## Done when

- [ ] Rotated-page word positions fixed and tested; BHEL re-ingested on the live URL.
- [ ] Set B scored by `score_b.py`: 5 of 5, or every miss written to `EVAL.md` §6; raw output in `eval/results/`.
- [ ] A1 on the live URL shows the red box on the right pumps, readings verified against the text layer, and R1 using the drawing's shared header (1.86 m/s OK, information note), with the drawing citation.
- [ ] A change with no drawing page still returns its verdict; the screen says why there is no drawing.
- [ ] CLAUDE.md, RULES.md, ARCHITECTURE.md updated with the drawing evidence rule.
- [ ] `pytest -q` green; change check still under 90 s (seconds per step in the commit message); `PHASES.md` phase 3 `done (phase-3-drawing)`, tag pushed, deployed.


---

## Amendments (approved 21 Nov; these override the text above)

From the phase 3 review and Bhargavi's decisions. Plan: `docs/specs/PHASE_3_PLAN.md`.

**A1 Set B scoring box.** `score_b.py` scores the **label_box** centre against the key box (the key holds the label's text-layer box), hit if within 0.03 of the page (`EVAL.md` §4). Not the item box.

**A2 No answer leak to the scorer.** Each B key gains `item_query` (B1 "SG Unit-1 floor wash water transfer pumps", B2 "SG Unit-2 floor wash water transfer pumps", B3 "MRS Unit-1 waste water transfer pumps", B4 "Transformer yard Unit-2 oily waste transfer pumps", B5 "SG Unit-3 floor wash water transfer pumps"), committed alone before any B run ("B keys: item_query added so the scorer never sees key notes"). The scorer uses only `item_query`; never `item`, `notes` or any other key field.

**A3 Line facts from the drawing only.** On a drawing page (`is_drawing`), `line_nb`, `line_role` and `shared_discharge` come only from verified drawing readings; text quotes from drawing pages are dropped for those three inputs (a bare "65NB" in the text layer does not say which line it labels: `EVAL.md` §6, A3).

**A4 Item box check.** The item box must contain the anchor label's words **including the unit tag token** (e.g. "UNIT-1"); otherwise `found` is overridden to false.

**B5 Engine and scenario.** `engine.py` applies the evidence gate to `source "drawing"` like `"document"`; `scenario._doc_value` passes the source through; `Value` gains an optional `box`.

**B6 Store.** Both stores gain `get_page_png`, `put_change_png`, `get_change_png`.

**B7 Crop.** `drawing.crop_fraction` 0.40 in `reading.yaml`; when a needed reading (line size, shared discharge) is missing from the crop, one more call on the whole sheet (downscaled) fills it.

**B8 Box format calibration.** Calibrate once on **ESP Unit-1 waste water transfer pumps** (Part3 p.146; not in set B): compare Argon's label box with its text-layer box, set the conversion in `reading.yaml` (`drawing.box_format`), record the result in `vision.py`'s docstring. **Never calibrate on a B item.**

**B9 PROJECT.md §4.** "the D5-200 band for the line's role" (the 200NB header may be a discharge header: header row 2.1-2.4 m/s).

**C10 Re-ingest.** `POST /plants/{id}/reingest` re-ingests the files already in the bucket (same plant id; pages, `pages_all.json`, PNGs rewritten; token count kept). Replaces "re-upload as a new plant" in §0 and §10.

**C11 Time.** The done-when "under 90 s" is measured after one warm-up check on the plant (the first check on a plant fills the automatic cache).

**C12 PHASES.md.** Phase 3 in progress with a pointer to this spec and its plan.
