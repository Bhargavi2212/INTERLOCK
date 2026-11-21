"""Find every page that mentions an item, to help write set A keys.

    python scripts/find_pages.py "floor wash" "FW pump" ["more names" ...] [--dir data/bhel]

Case-insensitive; spaces ignored ("floorwash" matches "floor wash").
Prints `file | page | line` for each hit, page 1-based within the file.
Hits are proposals only: a person reads every page before it goes in a key.
"""

import argparse
import re
import sys
from pathlib import Path

import pymupdf


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="+", help="item names and aliases")
    ap.add_argument("--dir", default="data/bhel", help="folder of PDFs (searched recursively)")
    args = ap.parse_args()

    folder = Path(args.dir)
    pdfs = sorted(folder.rglob("*.pdf"))
    if not pdfs:
        print(f"no PDFs found under {folder}")
        return 1

    targets = [(n, squash(n)) for n in args.names]
    hits_per_name = {n: 0 for n in args.names}
    pages_hit = set()

    for pdf in pdfs:
        rel = pdf.relative_to(folder).as_posix()
        with pymupdf.open(pdf) as doc:
            for i, page in enumerate(doc, start=1):
                for line in page.get_text().splitlines():
                    s = squash(line)
                    found = [n for n, t in targets if t and t in s]
                    if found:
                        for n in found:
                            hits_per_name[n] += 1
                        pages_hit.add((rel, i))
                        print(f"{rel} | {i} | {' '.join(line.split())[:140]}  [{', '.join(found)}]")

    print(f"\n{len(pages_hit)} pages with a hit, across {len(pdfs)} PDFs")
    for n, c in hits_per_name.items():
        print(f"  {n!r}: {c} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
