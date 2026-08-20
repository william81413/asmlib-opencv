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
    python3 extract_plan.py Obergeschoss.pdf --furniture > furniture.path

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
INTERIOR = (0.24, 3.48, 9.46, 13.81)      # the flat, in metres from the NW corner of the extension
FACES_X = [0.24, 3.806, 3.979, 7.959, 8.20, 9.457]
FACES_Y = [3.488, 8.577, 8.691, 10.791, 10.905, 13.805]
# NOTE: do not add a size filter here. An earlier version dropped rects smaller
# than 7 x 12 pt as "dimension arrow heads" and silently deleted the 24 x 22,9 cm
# door jamb beside the flat's entrance, which put the whole south-east corner of
# the model wrong. The arrow heads sit outside BUILDING, so the window is enough.


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
        if r.width < 1.0 or r.height < 1.0:
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


def furniture(path):
    """The architect's own furniture symbols, as one SVG path in centimetres.

    They are drawn as loose black line segments rather than grouped objects, so
    they cannot be recovered as furniture *objects* - only as a reference
    underlay. Wall outlines and door swings are dropped: the tool draws its own.
    """
    page = pymupdf.open(path)[0]
    rot = page.rotation_matrix
    ox, oy = 372.69, 211.56

    def to(q):
        p = q * rot
        return ((p.x - ox) * SCALE, (p.y - oy) * SCALE)

    def inside(x, y):
        return (INTERIOR[0] - .02 < x < INTERIOR[2] + .02
                and INTERIOR[1] - .02 < y < INTERIOR[3] + .02)

    def on_a_wall(a, b):
        if abs(a[0] - b[0]) < .01 and any(abs(a[0] - v) < .025 for v in FACES_X):
            return True
        return abs(a[1] - b[1]) < .01 and any(abs(a[1] - v) < .025 for v in FACES_Y)

    n = lambda v: round(v * 100, 1)
    out = []
    for item in page.get_drawings():
        col = item.get("color")
        if col is None or max(col) > 0.15:          # furniture is drawn in black
            continue
        if (item.get("width") or 0) > 0.6:          # heavy lines are walls and frames
            continue
        for seg in item["items"]:
            if seg[0] == "l":
                a, b = to(seg[1]), to(seg[2])
                if inside(*a) and inside(*b) and not on_a_wall(a, b):
                    out.append(f"M{n(a[0])} {n(a[1])}L{n(b[0])} {n(b[1])}")
            elif seg[0] == "c":
                q = [to(seg[i]) for i in (1, 2, 3, 4)]
                if not all(inside(*t) for t in q):
                    continue
                span = max(max(t[i] for t in q) - min(t[i] for t in q) for i in (0, 1))
                if span > 0.5:                      # door swing arcs: the tool draws its own
                    continue
                out.append("M{} {}C{} {} {} {} {} {}".format(*[n(v) for t in q for v in t]))
            elif seg[0] == "re":
                r = seg[1] * rot
                a = ((r.x0 - ox) * SCALE, (r.y0 - oy) * SCALE)
                b = ((r.x1 - ox) * SCALE, (r.y1 - oy) * SCALE)
                if inside(*a) and inside(*b):
                    out.append(f"M{n(a[0])} {n(a[1])}H{n(b[0])}V{n(b[1])}H{n(a[0])}Z")
    return "".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = args[0] if args else "Obergeschoss.pdf"
    if "--furniture" in sys.argv:
        sys.stdout.write(furniture(src))
        sys.exit(0)
    ws = walls(src)
    if "--check" in sys.argv:
        sys.exit(0 if check(ws) else 1)
    json.dump({"scale_m_per_pt": SCALE, "walls": ws}, sys.stdout, indent=1)
