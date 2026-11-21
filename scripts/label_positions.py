"""Where a label sits on a page, from the PDF's own text layer (set B keys).

    python scripts/label_positions.py data/bhel/Part3.pdf <page> "<label text>"
    python scripts/label_positions.py data/bhel/Part3.pdf --find "D3-146"

First form: every box of the phrase on that page (1-based), normalised 0-1 to
the page as displayed (rotation applied), plus its centre. Prints "not found"
if the phrase is not on the page. Second form: lists the pages whose text
contains the phrase (use it to find the page a drawing number is on).
A person checks every box on the page before it goes in a key. No model.
"""

import argparse
import sys

import pymupdf


def find_pages(doc, phrase: str) -> int:
    hits = [i for i, page in enumerate(doc, start=1) if page.search_for(phrase)]
    print(f"'{phrase}' on pages: {hits if hits else 'not found'}")
    return 0 if hits else 1


def boxes(doc, page_no: int, phrase: str) -> int:
    if not 1 <= page_no <= doc.page_count:
        print(f"page {page_no} out of range 1-{doc.page_count}")
        return 1
    page = doc[page_no - 1]
    w, h = page.rect.width, page.rect.height
    rects = page.search_for(phrase)
    print(f"page {page_no}: {w:.0f} x {h:.0f} pt, rotation {page.rotation}")
    if not rects:
        print("not found")
        return 1
    for r in rects:
        r = r * page.rotation_matrix  # to displayed orientation
        r.normalize()
        box = [r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h]
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        print(f"box [{box[0]:.4f}, {box[1]:.4f}, {box[2]:.4f}, {box[3]:.4f}]  centre ({cx:.4f}, {cy:.4f})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("page", nargs="?", type=int, help="1-based page number")
    ap.add_argument("phrase", nargs="?", help="label text as printed")
    ap.add_argument("--find", metavar="PHRASE", help="list pages containing PHRASE")
    args = ap.parse_args()

    with pymupdf.open(args.pdf) as doc:
        if args.find:
            return find_pages(doc, args.find)
        if args.page is None or not args.phrase:
            ap.error("give <page> and <label text>, or --find PHRASE")
        return boxes(doc, args.page, args.phrase)


if __name__ == "__main__":
    sys.exit(main())
