#!/usr/bin/env python3
"""Generate read/usfm.css from the Paratext default USFM stylesheets.

Sources (pinned by commit, verified by sha256; the .sty files are not committed
because their upstream licence is not stated, so they are fetched on demand):
  usfm3_1.sty  usfm-bible/tcdocs  grammar/usfm3_1.sty  @ f4e35e8fdcd1 (USFM 3.1, primary)
  usfm.sty     ubsicap/usfm       sty/usfm.sty         @ 69838c870133 (Version=3.0.11, Paratext default; fallback)

Mapping (one CSS rule per \\Marker, class .usfm-<marker>):
  \\FontSize N        -> font-size: N/12 em   (12 pt is the sty body size = 1em)
  \\Bold / \\Italic    -> font-weight:bold / font-style:italic
  \\Underline         -> text-decoration:underline
  \\Smallcaps         -> font-variant:small-caps
  \\Superscript       -> vertical-align:super; font-size:.66em (Paratext superscript)
  \\Subscript         -> vertical-align:sub; font-size:.66em
  \\Color N           -> color (N is a Windows COLORREF 0x00BBGGRR)
  \\Justification X   -> text-align (Both -> justify)
  \\SpaceBefore/After pt -> margin-top/bottom: pt/12 em
  \\LeftMargin/RightMargin/FirstLineIndent inches -> calc(N * var(--usfm-inch))
                       (1 in = 72 pt = 6em at 12 pt; the reader narrows this on phones)
  \\TextProperties nonpublishable -> display:none
AIV overrides are listed in OVERRIDES below, each with its reason, and are
emitted after the generated rules so the sty value stays visible in the file.

Usage: python3 tools/sty2css.py [--sty-dir DIR] [-o read/usfm.css]
"""
import argparse, hashlib, pathlib, re, sys, urllib.request

SOURCES = {
    "usfm3_1.sty": ("https://raw.githubusercontent.com/usfm-bible/tcdocs/"
                    "f4e35e8fdcd112eb0eecd489ce409c2f5b01452b/grammar/usfm3_1.sty",
                    "55f7aa806ca8c37e45ee0beb04d88e073555647dd79e36822b5da54263c3c83a"),
    "usfm.sty": ("https://raw.githubusercontent.com/ubsicap/usfm/"
                 "69838c870133bb0c9f7b42f741053c08cd7b29e0/sty/usfm.sty",
                 "cc6a55dd25f7a5b8fb0f7417824f97923d67899ce2317e0c3b0910835c7cd393"),
}

# AIV-specific deviations from the Paratext defaults. Keep this list short.
OVERRIDES = {
    "add": ({"font-weight": "normal"},
            "sty gives add Bold+Italic; the AIV USX header (rem) declares "
            "char:add=translator-addition-italic, so supplied words are italic only"),
    "wj": ({"color": "inherit"},
           "sty gives wj Color 255 (red); Kevin ruled 14 Nov 2026: no red letters, "
           "words of Jesus in normal ink"),
    "d": ({"font-style": "normal", "font-variant-caps": "small-caps", "text-align": "left"},
          "sty gives d Italic, centred; Kevin ruled 14 Nov 2026: superscriptions/colophons in small caps, "
          "no italics (supplied words keep add italic), left-aligned"),
    "qd": ({"font-style": "normal", "font-variant-caps": "small-caps", "text-align": "left", "margin-left": "0"},
           "sty gives qd Italic, indented; Kevin ruled 14 Nov 2026: small caps, no italics "
           "(supplied words keep add italic), flush left"),
}


def load(sty_dir: pathlib.Path, name: str) -> str:
    url, sha = SOURCES[name]
    p = sty_dir / name
    if not p.exists():
        sty_dir.mkdir(parents=True, exist_ok=True)
        p.write_bytes(urllib.request.urlopen(url).read())
    data = p.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != sha:
        sys.exit(f"{p}: sha256 {got} != pinned {sha}")
    return data.decode("utf-8")


def parse(text: str) -> dict:
    styles, cur = {}, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        m = re.match(r"\\(\w+)\s*(.*)", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "Marker":
            cur = styles.setdefault(val, {"Marker": val})
        elif cur is not None and key not in ("OccursUnder",):
            cur[key] = val
    return styles


def num(v):
    return float(v.split()[0])


def fmt(x):
    return ("%.4f" % x).rstrip("0").rstrip(".")


def colorref(n: int) -> str:
    r, g, b = n & 255, (n >> 8) & 255, (n >> 16) & 255
    return f"#{r:02x}{g:02x}{b:02x}"


def rule(st: dict) -> dict:
    css = {}
    props = st.get("TextProperties", "").split()
    if "nonpublishable" in props:
        css["display"] = "none"
    if "FontSize" in st:
        css["font-size"] = fmt(num(st["FontSize"]) / 12) + "em"
    if "Bold" in st:
        css["font-weight"] = "bold"
    if "Italic" in st:
        css["font-style"] = "italic"
    if "Underline" in st:
        css["text-decoration"] = "underline"
    if "Smallcaps" in st:
        css["font-variant"] = "small-caps"
    if "Superscript" in st:
        css["vertical-align"] = "super"; css["font-size"] = ".66em"; css["line-height"] = "0"
    if "Subscript" in st:
        css["vertical-align"] = "sub"; css["font-size"] = ".66em"; css["line-height"] = "0"
    if "Color" in st:
        css["color"] = colorref(int(num(st["Color"])))
    if "Justification" in st:
        j = st["Justification"].lower()
        css["text-align"] = {"both": "justify"}.get(j, j)
    if st.get("StyleType", "").lower() == "paragraph":
        for k, prop in (("SpaceBefore", "margin-top"), ("SpaceAfter", "margin-bottom")):
            if k in st:
                css[prop] = fmt(num(st[k]) / 12) + "em"
        for k, prop in (("LeftMargin", "margin-left"), ("RightMargin", "margin-right"),
                        ("FirstLineIndent", "text-indent")):
            if k in st:
                css[prop] = f"calc({fmt(num(st[k]))} * var(--usfm-inch))"
    return css


def main():
    ap = argparse.ArgumentParser()
    root = pathlib.Path(__file__).resolve().parent.parent
    ap.add_argument("--sty-dir", default=str(root / "tools" / ".sty-cache"))
    ap.add_argument("-o", "--out", default=str(root / "read" / "usfm.css"))
    a = ap.parse_args()
    d = pathlib.Path(a.sty_dir)
    primary, fallback = parse(load(d, "usfm3_1.sty")), parse(load(d, "usfm.sty"))
    out = [
        "/* GENERATED by tools/sty2css.py. Do not edit by hand. */",
        "/* Source: usfm3_1.sty (usfm-bible/tcdocs @ f4e35e8fdcd1, sha256 55f7aa80...), */",
        "/* fallback usfm.sty Version=3.0.11 (ubsicap/usfm @ 69838c870133, sha256 cc6a55dd...), */",
        "/* the Paratext default stylesheet. One rule per \\Marker: .usfm-<marker>. */",
        ":root{--usfm-inch:6em}",
    ]
    markers = list(primary) + [m for m in fallback if m not in primary]
    for m in markers:
        st = primary.get(m) or fallback[m]
        css = rule(st)
        if not css:
            continue
        cls = ".usfm-" + re.sub(r"[^A-Za-z0-9_-]", "_", m)
        src = "3.1" if m in primary else "3.0.11"
        body = ";".join(f"{k}:{v}" for k, v in css.items())
        out.append(f"{cls}{{{body}}} /* {src}: {st.get('Name', m)} */")
    out.append("/* AIV overrides */")
    for m, (css, why) in OVERRIDES.items():
        body = ";".join(f"{k}:{v}" for k, v in css.items())
        out.append(f".usfm-{m}{{{body}}} /* {why} */")
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {a.out}: {len(out) - 6} rules from {len(markers)} markers")


if __name__ == "__main__":
    main()
