#!/usr/bin/env python3
"""
Google Fonts -> one self-contained <style> block of base64 @font-face rules.

The tool is meant to be opened by double-clicking a file, so it must not need a
network. This pulls the woff2 files the sheet's typography uses and inlines
them, which removes the last external reference in index.html.

Two things matter and are easy to get wrong:

  * Google Fonts serves ttf, not woff2, unless the request carries a modern
    browser User-Agent. woff2 is roughly a third of the size.
  * Archivo and IBM Plex Sans are variable fonts, so all three weights of each
    resolve to the SAME woff2 URL. De-duplicate by URL or the file triples in
    size for nothing.

Only the `latin` subset is taken: the interface is English and the room names
are German, both of which live in latin.

    python3 embed_fonts.py > fonts.css        # the block, ready to paste
    python3 embed_fonts.py --check            # sizes only, downloads nothing extra
"""
import base64
import re
import sys
import urllib.request

CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Archivo:wght@500;600;700"
    "&family=IBM+Plex+Mono:wght@400;500;600"
    "&family=IBM+Plex+Sans:wght@400;500;600"
    "&display=swap"
)
# without this the API hands back ttf
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def latin_faces():
    """[(family, weight, url)] for the latin subset, in stylesheet order."""
    css = get(CSS_URL, {"User-Agent": UA}).decode()
    out = []
    for subset, body in re.findall(r"/\* ([^*]+) \*/\s*@font-face \{(.*?)\}", css, re.S):
        if subset.strip() != "latin":
            continue
        out.append((
            re.search(r"font-family: '([^']+)'", body).group(1),
            re.search(r"font-weight: (\d+)", body).group(1),
            re.search(r"url\((https[^)]+)\)", body).group(1),
        ))
    if not out:
        sys.exit("no latin faces found - did the Google Fonts response change?")
    return out


def main():
    faces = latin_faces()
    blobs, total = {}, 0                       # url -> bytes, fetched once each
    for _, _, url in faces:
        if url in blobs:
            continue
        blobs[url] = get(url)
        total += len(blobs[url])

    if "--check" in sys.argv:
        for url, data in blobs.items():
            who = ", ".join(f"{f} {w}" for f, w, u in faces if u == url)
            print(f"{len(data):7d} B  {who}", file=sys.stderr)
        print(f"---\n{len(blobs)} unique files, {total/1024:.1f} KB raw, "
              f"~{total*4/3/1024:.1f} KB as base64", file=sys.stderr)
        return

    # One rule per FILE, not per weight. A variable font covers several weights
    # from the same woff2; emitting it once per weight would triple the base64
    # for nothing. CSS takes a range, so the weights collapse into one rule.
    order, weights, family_of = [], {}, {}
    for family, weight, url in faces:
        if url not in weights:
            order.append(url)
            weights[url] = []
            family_of[url] = family
        weights[url].append(int(weight))

    rules = []
    for url in order:
        ws = sorted(weights[url])
        span = str(ws[0]) if len(ws) == 1 else f"{ws[0]} {ws[-1]}"
        b64 = base64.b64encode(blobs[url]).decode()
        rules.append(
            f"@font-face{{font-family:'{family_of[url]}';font-style:normal;"
            f"font-weight:{span};font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
        )
    out = "".join(rules)
    sys.stdout.write(out)
    print(f"{len(faces)} faces from {len(blobs)} files -> {len(rules)} rules, "
          f"{total/1024:.1f} KB raw, {len(out)/1024:.1f} KB emitted", file=sys.stderr)


if __name__ == "__main__":
    main()
