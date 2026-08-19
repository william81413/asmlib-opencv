#!/usr/bin/env python3
"""
Obergeschoss.pdf -> wall geometry.

The architect's PDF is a vector drawing, not a scan, and its layers are colour
coded the way German construction drawings are:

    grey  (0.875)      Bestand   existing walls
    red   (0.961,0,0)  Neu       new walls
    yellow(1,1,0)      Abbruch   demolition

so the walls can be read straight out of the page's drawing operators. No image
processing is involved. Output is a list of axis-aligned wall rectangles in
metres, origin at the north-west corner of the extension.

    pip install pymupdf
    python3 extract_plan.py Obergeschoss.pdf > walls.json

Verification (run with --check): every wall thickness must land on one of the
thicknesses annotated in the drawing (24 / 17.5 / 11.5 cm), and the derived
axis lines must reproduce the drawing's own dimension chain
24 + 3,56.5 + 17.5 + 3,98 + 24 + 2,31.5 + 24 = 10,75.5 m.
"""
import json
import sys

import pymupdf

SCALE = 0.0352778          # metres per PDF point at 1:100 on A3 (25.4/72/1000*100)
BUILDING = (350, 700, 200, 620)   # page-space window that excludes legend + title block


def classify(fill):
    if fill is None:
        return None
    r, g, b = fill
    if abs(r - 0.875) < 0.02 and abs(g - 0.875) < 0.02:
        return "bestand"
    if r > 0.9 and g < 0.1 and b < 0.1:
        return "neu"
    if r > 0.9 and g > 0.9 and b < 0.1:
        return "abbruch"
    return None


def walls(path):
    page = pymupdf.open(path)[0]
    rot = page.rotation_matrix          # the sheet is stored portrait, rotated 90 deg
    x0, x1, y0, y1 = BUILDING
    out = []
    for item in page.get_drawings():
        kind = classify(item.get("fill"))
        if not kind:
            continue
        r = item["rect"] * rot
        if not (x0 < r.x0 < x1 and y0 < r.y0 < y1):
            continue
        if r.width < 1.5 or r.height < 1.5:
            continue
        if r.width < 7 and r.height < 12:       # dimension arrow heads
            continue
        out.append({"kind": kind, "r": [r.x0, r.y0, r.x1, r.y1]})
    ox = min(w["r"][0] for w in out)
    oy = min(w["r"][1] for w in out)
    for w in out:
        a, b, c, d = w["r"]
        w["r"] = [round((a - ox) * SCALE, 4), round((b - oy) * SCALE, 4),
                  round((c - ox) * SCALE, 4), round((d - oy) * SCALE, 4)]
        w["t"] = round(min(c - a, d - b) * SCALE, 4)
    return out


def axis_lines(ws, horizontal):
    vals = sorted(v for w in ws for v in (w["r"][0], w["r"][2]) ) if not horizontal else \
           sorted(v for w in ws for v in (w["r"][1], w["r"][3]))
    groups = [[vals[0]]]
    for v in vals[1:]:
        (groups[-1] if v - groups[-1][-1] <= 0.05 else groups.append([]) or groups[-1]).append(v)
    return [round(sum(g) / len(g), 3) for g in groups]


def check(ws):
    ok = True
    chain = [0.24, 3.565, 0.175, 3.98, 0.24, 2.315, 0.24]
    want, acc = [], 0.0
    for seg in chain:
        acc += seg
        want.append(round(acc, 3))
    have = axis_lines(ws, horizontal=False)
    for w in want:
        if not any(abs(w - h) < 0.02 for h in have):
            print(f"  MISS  dimension chain line at {w:.3f} m not found", file=sys.stderr)
            ok = False
    print(f"  dimension chain: {sum(1 for w in want if any(abs(w-h)<0.02 for h in have))}/{len(want)} lines matched",
          file=sys.stderr)
    for t in {w["t"] for w in ws}:
        if not any(abs(t - n) < 0.02 for n in (0.115, 0.175, 0.24, 0.37)):
            print(f"  note  unexpected wall thickness {t*100:.1f} cm", file=sys.stderr)
    return ok


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    ws = walls(args[0] if args else "Obergeschoss.pdf")
    if "--check" in sys.argv:
        sys.exit(0 if check(ws) else 1)
    json.dump({"scale_m_per_pt": SCALE, "walls": ws}, sys.stdout, indent=1)
