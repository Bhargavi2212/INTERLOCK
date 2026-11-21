# Set E item sheet (prepared 21 Nov, 12:35)

Prepared by Claude (reviewer) from text search of the five BHEL PDFs plus one look at P&ID D3-146.
No Interlock code was run. **This is not a key.** A key exists only when a person at the event has
typed a change and `eval/keys/E*.json` is committed.

Pages are `file p.N` (N = page inside that file). Printed "Page X of 851" = Part1 N, Part2 150+N,
Part3 300+N, Part4 450+N, Part5 600+N.

## How to collect one key (about 3 minutes per person)

1. Show the person the list below. They pick one item.
2. They type one change in their own words. Copy it exactly, typos included.
3. Copy that item's row into the JSON template at the bottom, open the pages together, add the
   expected verdict, commit.

Do not offer SG Unit-1 or MRS Unit-1 (they are set A, the development set).

## Items (scope list: Part1 p.43-44; data sheet: Part4 p.53-61; P&ID: Part3 p.146)

| # | Item (scope name) | Scope | Data sheet | P&ID (Part3 p.146) | Documents agree? |
|---|---|---|---|---|---|
| 1 | Transformer yard Unit-1 oily waste transfer pumps | Part1 p.43: 2 nos (1W+1S) | Part4 p.55: 1W+1S, 10 m3/h, vertical screw; sump E4, volume not stated | 10 M3/HR (1W+1S) | yes |
| 2 | Transformer yard Unit-2 oily waste transfer pumps | Part1 p.43: 1W+1S | Part4 p.55-56: 1W+1S, 10 m3/h; sump E5, volume not stated | 10 M3/HR (1W+1S) | yes |
| 3 | TG Unit-1A waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.53, named "floor wash water transfer pumps": 1W+1S, 25 m3/h; sump E1A 12 m3 | check label on drawing | name differs |
| 4 | TG Unit-1B waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.53: 1W+1S, 25 m3/h; sump E1B 12 m3 | 25 M3/HR (1W+1S); sump 12 M3 | name differs |
| 5 | TG Unit-2A waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.54: 1W+1S, 25 m3/h; sump E2A 12 m3. Sump says TDBFP-B Unit-2, pump says TDBFP-A Unit-2 | 25 M3/HR (1W+1S); sump 12 M3 | fluid source differs inside the data sheet |
| 6 | TG Unit-2B waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.55 (sump E2B on p.54): 1W+1S, 25 m3/h; sump 12 m3 | 25 M3/HR (1W+1S); sump 12 M3 | name differs |
| 7 | MRS Unit-2 waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.57, named "oily waste water transfer pumps": 1W+1S, 10 m3/h, vertical centrifugal; sump E7 10 m3 (p.56-57). Pump fluid says "Unit-1" | check values on drawing | pump fluid says Unit-1 for a Unit-2 pump |
| 8 | ESP Unit-1 waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.58, named "floor wash water transfer pumps": 1W+1S, 50 m3/h; sump E10 50 m3 | 50 M3/HR (1W+1S); sump 50 M3 | name differs |
| 9 | ESP Unit-2 waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.59 (sump E11 on p.58-59): 1W+1S, 50 m3/h; sump 50 m3 | 50 M3/HR (1W+1S); sump 50 M3 | name differs |
| 10 | SG Unit-2 waste water transfer pumps | Part1 p.43: **1W+1S** | Part4 p.58, named "floor wash water transfer pumps": **Two (2W)**, 105 m3/h; sump E9 105 m3. Fluid text says "SG UNIT 1" | **105M3/HR (2W)**; sump 105 M3; 200NB lines | **no: 1W+1S vs 2W** |
| 11 | COT/DOT waste water transfer pumps | Part1 p.43: 1W+1S | Part4 p.54: 1W+1S, 2 m3/h, horizontal screw; sump E1C 1 m3 | 2 M3/HR (1W+1S); sump 1 M3 | yes |
| 12 | Trolley mounted screw pumps | Part1 p.43: 2 nos (2W) | Part4 p.61: 2W, 10 m3/h, head 15 mwc; slope oil tank 1 m3 | "CAP. 10M3, (2NOS.)" | unit differs (m3 vs m3/h) |
| 13 | WSWS transfer pumps | Part1 p.43: 3 nos (2W+1S) | Part4 p.59: 2W+1S, 125 m3/h, vertical centrifugal; sump E12 250 m3 each compartment | (3X50%), 125 M3/HR each | yes |
| 14 | Central monitoring basin (CMB) transfer pumps | Part1 p.44: 3 nos (2W+1S) | Part4 p.60: 2W+1S, 125 m3/h, horizontal centrifugal; basin E13 250 m3 each. Fluid says "Effluent from WSWS" | (3X50%), 125 M3/HR each | fluid text looks copied |
| 15 | Sludge sump transfer pumps | Part1 p.44: 2 nos (1W+1S) | Part4 p.61: 1W+1S, 12.5 m3/h; sump E14 6.25 m3 each. Fluid says "Effluent from WSWS" | (2X100%), 12.5 M3/H | fluid text looks copied |

Also on every key: pipe run lengths are on Part1 p.45-46; velocity limits are on Part5 p.200
(pump discharge: below 50 mm 1.2-1.8, 50-150 mm 1.8-2.4, 200 mm and above 2.1-2.5 m/s).

Not checked here: which NB label belongs to which pump for items 1-9 and 11-15. Read it off the
drawing with the author when the change touches flow or line size.

## Expected verdict, as a guide (the author and Bhargavi decide)

- More working pumps with the same number installed: standby fails, so BLOCK.
- Any change to item 10: the documents already disagree, so BLOCK.
- A flow or line-size change where the line size cannot be read for that pump: REVIEW.
- Sump inflow is not stated anywhere, so the sump check is held on every item.

## Template

Pre-filled skeletons for all 15 items, in this format, are in `eval/E_prefill.json`.

```json
{"id": "E1", "author": "first name", "written_at": "HH:MM",
 "change": "text exactly as the author wrote it",
 "expected_pages": [{"file": "Part1.pdf", "page": 43}, {"file": "Part4.pdf", "page": 59}],
 "expected_values": [{"attribute": "working pumps", "value": "2", "unit": "count", "file": "Part1.pdf", "page": 43}],
 "documents_disagree": false,
 "expected_verdict": "BLOCK"}
```
