#!/usr/bin/env python3
"""Build the human-readable AIV reader (read/) from usx/*.usx.

Renders exactly what is in the USX: every publishable paragraph, character
style and footnote, in source order, with no change to wording. Styles come
from read/usfm.css, which tools/sty2css.py generates from the Paratext default
stylesheets. Layout and chrome live in read/reader.css (hand-written).

Output (served by Cloudflare Pages with pretty URLs):
  _redirects                 /read, /read/{BOOK} -> 301 to the first chapter
  read/{BOOK}/{N}.html       one chapter        -> /read/GEN/1
The raw USX, manifest.json, books.json and metadata.json are left untouched.

Usage: python3 tools/sty2css.py && python3 tools/build_reader.py && python3 tools/verify_reader.py
"""
import hashlib, html, json, pathlib, re, shutil, sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sty2css  # noqa: E402

OUT = ROOT / "read"
CREDIT = "based on a public-domain draft published at literalbible.com, with AIV corrections"

# Same grouping and order as the site index (Tanakh order for the Old Testament).
GROUPS = [
    ("Old Testament", "The Law (TORAH)", "GEN EXO LEV NUM DEU"),
    ("Old Testament", "The Prophets (NEVI’IM)",
     "JOS JDG 1SA 2SA 1KI 2KI ISA JER EZK HOS JOL AMO OBA JON MIC NAM HAB ZEP HAG ZEC MAL"),
    ("Old Testament", "The Writings (KETUVIM)", "PSA PRO JOB SNG RUT LAM ECC EST DAN EZR NEH 1CH 2CH"),
    ("New Testament", None,
     "MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV"),
]
ORDER = [b for _, _, s in GROUPS for b in s.split()]

# Paragraph markers rendered as apparatus (editorial headings), not Scripture:
# everything the sty types as Section or Title, plus the acrostic letter line.
def load_sty():
    d = ROOT / "tools" / ".sty-cache"
    p = sty2css.parse(sty2css.load(d, "usfm3_1.sty"))
    f = sty2css.parse(sty2css.load(d, "usfm.sty"))
    return {**f, **p}

STY = load_sty()

def publishable(style):
    return "nonpublishable" not in STY.get(style, {}).get("TextProperties", "").split()

def is_apparatus(style):
    return STY.get(style, {}).get("TextType") in ("Section", "Title") or style == "qa"

HEADING_TAG = {"ms": "h2", "ms1": "h2", "ms2": "h2", "ms3": "h2", "s": "h3", "s1": "h3",
               "s2": "h4", "s3": "h4", "s4": "h4"}

esc = lambda s: html.escape(s or "", quote=False)
attr = lambda s: html.escape(s or "", quote=True)


def letters(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(97 + r) + s
    return s


class Chapter:
    def __init__(self, n):
        self.n, self.paras, self.notes = n, [], []


class Renderer:
    def __init__(self, ch):
        self.ch, self.unknown = ch, set()

    def inline(self, el):
        out = [esc(el.text)]
        for c in el:
            out.append(self.node(c))
            out.append(esc(c.tail))
        return "".join(out)

    def node(self, c):
        tag, st = c.tag, c.get("style", "")
        if tag == "verse":
            if c.get("sid") is None:
                return ""
            n = c.get("number")
            s = f'<sup class="usfm-v vn" id="v{attr(n)}">{esc(n)}</sup>'
            if c.get("altnumber"):
                s += f'<sup class="usfm-va vn">{esc(c.get("altnumber"))}</sup>'
            return s
        if tag == "char":
            return f'<span class="usfm-{attr(st)}">{self.inline(c)}</span>'
        if tag == "note":
            k = len(self.ch.notes)
            caller = c.get("caller", "+")
            mark = letters(k) if caller in ("+", "-") else caller
            body = self.inline(c)
            self.ch.notes.append((k, mark, st, body))
            return (f'<a class="fn-call" href="#fn{k + 1}" id="fnr{k + 1}" '
                    f'aria-label="note {esc(mark)}"><sup>{esc(mark)}</sup></a>')
        self.unknown.add(tag)
        return f'<span class="usx-{attr(tag)} usfm-{attr(st)}">{self.inline(c)}</span>'


def parse_book(path):
    root = ET.parse(path).getroot()
    intro, chapters, cur, unknown = Chapter(0), [], None, set()
    for el in root:
        if el.tag == "chapter":
            if el.get("sid"):
                cur = Chapter(int(el.get("number")))
                chapters.append(cur)
            else:
                cur = None
            continue
        if el.tag not in ("para", "book"):
            unknown.add(el.tag)
        if el.tag != "para" or not publishable(el.get("style", "")):
            continue
        target = cur if cur else (intro if not chapters else None)
        if target is None:
            sys.exit(f"{path.name}: paragraph outside any chapter after chapter {chapters[-1].n}; "
                     "extend build_reader.py before publishing")
        r = Renderer(target)
        target.paras.append((el.get("style"), r.inline(el)))
        unknown |= r.unknown
    if intro.notes:
        sys.exit(f"{path.name}: footnote before chapter 1; extend build_reader.py")
    return intro, chapters, unknown


def para_html(st, body, extra=""):
    kind = "apparatus" if is_apparatus(st) else "scripture"
    tag = HEADING_TAG.get(st, "p")
    return f'<{tag} class="usfm-{attr(st)} {kind}{extra}">{body}</{tag}>'


HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vollkorn:ital,wght@0,400..900;1,400..900&family=Vollkorn+SC:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/read/usfm.css">
<link rel="stylesheet" href="/read/reader.css">
<script src="/read/nav-data.js" defer></script>
<script src="/read/reader.js" defer></script>
{extra}</head>
<body data-book="{book}" data-chapter="{chapter}">
<div class="page">
<header class="bar">
<button class="bar-btn menu" type="button" aria-label="Open the book list" aria-controls="panel" aria-expanded="false" data-open="panel"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
<a class="bar-title" href="{barhref}" aria-controls="panel" aria-expanded="false" data-open="panel" title="Choose a book and chapter">{bartitle}</a>
<span class="bar-right"><a class="status" href="/" title="Amundson Interpretive Version: a draft">DRAFT</a><button class="bar-btn search" type="button" aria-label="Search for a book or chapter" aria-controls="panel" aria-expanded="false" data-open="search"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="2" fill="none"/><path d="M15.5 15.5L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></span>
</header>
"""


def foot(source_links, fabs=""):
    return f"""<footer class="site">
<p class="draft">The AIV is a work in progress. It is not finished, and its wording may change.</p>
<p>Amundson Interpretive Version (AIV), {esc(CREDIT)}.</p>
<p>&copy; 2026 Kevin Amundson. Licensed under <a href="/LICENSE">CC BY 4.0</a>. {source_links}</p>
</footer>
</div>
{fabs}</body>
</html>
"""


def fabs(prev, nxt):
    """Floating round prev/next chapter buttons (bottom corners); omitted at GEN 1 / REV 22."""
    out = []
    if prev:
        out.append(f'<a class="fab prev" rel="prev" href="/read/{prev[0]}/{prev[1]}" '
                   f'aria-label="Previous chapter: {attr(prev[2])}" title="{attr(prev[2])}">'
                   '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M15 5l-7 7 7 7" '
                   'stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></a>\n')
    if nxt:
        out.append(f'<a class="fab next" rel="next" href="/read/{nxt[0]}/{nxt[1]}" '
                   f'aria-label="Next chapter: {attr(nxt[2])}" title="{attr(nxt[2])}">'
                   '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M9 5l7 7-7 7" '
                   'stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></a>\n')
    return "".join(out)


_BOOK_NAMES = None


def ref_target(body, book):
    """Link target for an mr/sr/r reference: /read/{BOOK}/{chapter} of the first passage
    cited. A bare range such as (1:1-2:4) cites the current book; a named reference
    such as 'Genesis 1:1' cites that book. Returns None when no chapter can be read."""
    global _BOOK_NAMES
    if _BOOK_NAMES is None:
        books = {b["id"]: b["name"] for b in json.loads((ROOT / "books.json").read_text())}
        _BOOK_NAMES = {name: code for code, name in books.items()}
        _BOOK_NAMES.update({"Psalm": "PSA", "Song of Solomon": "SNG"})
    text = html.unescape(re.sub(r"<[^>]+>", "", body or "")).strip().lstrip("(").strip()
    code, rest = book, text
    for name in sorted(_BOOK_NAMES, key=len, reverse=True):
        if text.lower().startswith(name.lower()):
            code, rest = _BOOK_NAMES[name], text[len(name):].strip()
            break
    m = re.search(r"\d+", rest)
    if not m:
        return None
    return f"/read/{code}/{int(m.group())}"


def para_html(st, body, extra="", book=None):
    kind = "apparatus" if is_apparatus(st) else "scripture"
    tag = HEADING_TAG.get(st, "p")
    if st in ("mr", "sr", "r") and book:
        href = ref_target(body, book)
        if href:
            body = f'<a href="{href}">{body}</a>'
    return f'<{tag} class="usfm-{attr(st)} {kind}{extra}">{body}</{tag}>'


# The bar sits outside .page (Kevin 15 Nov): full width, menu top-left, search top-right.
HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vollkorn:ital,wght@0,400..900;1,400..900&family=Vollkorn+SC:wght@400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/read/usfm.css">
<link rel="stylesheet" href="/read/reader.css">
<script src="/read/nav-data.js" defer></script>
<script src="/read/reader.js" defer></script>
{extra}</head>
<body data-book="{book}" data-chapter="{chapter}">
<header class="bar">
<button class="bar-btn menu" type="button" aria-label="Open the book list" aria-controls="panel" aria-expanded="false" data-open="panel"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>
<a class="bar-title" href="{barhref}" aria-controls="panel" aria-expanded="false" data-open="panel" title="Choose a book and chapter">{bartitle}</a>
<span class="bar-right"><a class="status" href="/" title="Amundson Interpretive Version: a draft">DRAFT</a><button class="bar-btn search" type="button" aria-label="Search for a book or chapter" aria-controls="panel" aria-expanded="false" data-open="search"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" stroke="currentColor" stroke-width="2" fill="none"/><path d="M15.5 15.5L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></span>
</header>
<div class="page">
"""


def foot(source_links, fabs=""):
    return f"""<footer class="site">
<p class="draft">The AIV is a work in progress. It is not finished, and its wording may change.</p>
<p>Amundson Interpretive Version (AIV), {esc(CREDIT)}.</p>
<p>&copy; 2026 Kevin Amundson. Licensed under <a href="/LICENSE">CC BY 4.0</a>. {source_links}</p>
</footer>
</div>
{fabs}</body>
</html>
"""


def fabs(prev, nxt):
    """Floating round prev/next chapter buttons (bottom corners); omitted at GEN 1 / REV 22."""
    out = []
    if prev:
        out.append(f'<a class="fab prev" rel="prev" href="/read/{prev[0]}/{prev[1]}" '
                   f'aria-label="Previous chapter: {attr(prev[2])}" title="{attr(prev[2])}">'
                   '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M15 5l-7 7 7 7" '
                   'stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></a>\n')
    if nxt:
        out.append(f'<a class="fab next" rel="next" href="/read/{nxt[0]}/{nxt[1]}" '
                   f'aria-label="Next chapter: {attr(nxt[2])}" title="{attr(nxt[2])}">'
                   '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true"><path d="M9 5l7 7-7 7" '
                   'stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></a>\n')
    return "".join(out)


DROP_FROM = '<sup class="usfm-v vn" id="v1">1</sup>'


def dropcap(n):
    """Verse 1 shown as the large chapter number; screen readers hear 'Chapter n, verse 1'."""
    return (f'<span class="usfm-v vn dropcap" id="v1"><span class="sr">Chapter </span>{n}'
            f'<span class="sr">, verse 1</span></span>')


def build():
    books = {b["id"]: b["name"] for b in json.loads((ROOT / "books.json").read_text())}
    assert sorted(books) == sorted(ORDER), "books.json and reader order differ"
    for d in OUT.iterdir() if OUT.exists() else []:
        if d.is_dir() and d.name in books:
            shutil.rmtree(d)
    parsed, unknown = {}, set()
    for b in ORDER:
        intro, chs, unk = parse_book(ROOT / "usx" / f"{b}.usx")
        parsed[b] = (intro, chs)
        unknown |= unk
    seq = [(b, ch.n) for b in ORDER for ch in parsed[b][1]]
    lab = lambda b, n: f"Psalm {n}" if b == "PSA" else f"{books[b]} {n}"
    testament = {b: ("NT" if t == "New Testament" else "OT") for t, _, s in GROUPS for b in s.split()}
    data = [[b, books[b], len(parsed[b][1]), testament[b]] for b in ORDER]
    (OUT / "nav-data.js").write_text(
        "/* Generated by tools/build_reader.py: [id, name, chapters, testament] in reading order. */\n"
        "window.AIV_BOOKS=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8")
    # Cache-busting: CSS/JS are served with max-age=14400, HTML with max-age=0, so each
    # asset link carries a short hash of its content; a changed file gets a new URL at once.
    global HEAD
    for asset in ("usfm.css", "reader.css", "nav-data.js", "reader.js"):
        v = hashlib.sha256((OUT / asset).read_bytes()).hexdigest()[:10]
        HEAD = HEAD.replace(f'"/read/{asset}"', f'"/read/{asset}?v={v}"')
    pages = 0
    for i, (b, n) in enumerate(seq):
        intro, chs = parsed[b]
        ch = next(c for c in chs if c.n == n)
        prev = (seq[i - 1][0], seq[i - 1][1], lab(*seq[i - 1])) if i else None
        nxt = (seq[i + 1][0], seq[i + 1][1], lab(*seq[i + 1])) if i + 1 < len(seq) else None
        parts = [HEAD.format(title=f"{esc(lab(b, n))} · AIV (draft)",
                             desc=f"{attr(lab(b, n))} in the Amundson Interpretive Version (AIV), a draft English Bible text.",
                             extra=f'<link rel="alternate" type="application/xml" href="/usx/{b}.usx" title="USX source">\n',
                             book=b, chapter=n, barhref="/#books", bartitle=esc(lab(b, n))),
                 f'<main class="text" lang="en" data-book="{b}" data-chapter="{n}">\n']
        if n == chs[0].n:
            parts += [para_html(s, body, book=b) + "\n" for s, body in intro.paras]
        parts += [para_html(s_, body, book=b) + "\n" for s_, body in ch.paras]
        parts.append("</main>\n")
        if ch.notes:
            parts.append('<section class="notes" aria-label="Notes">\n<h2 class="chrome">Notes</h2>\n<ol>\n')
            for k, mark, st, body in ch.notes:
                parts.append(f'<li id="fn{k + 1}"><a class="fn-back" href="#fnr{k + 1}" '
                             f'aria-label="back to text">{esc(mark)}</a> '
                             f'<span class="usfm-{attr(st)} note-body">{body}</span></li>\n')
            parts.append("</ol>\n</section>\n")
        parts.append(foot(f'Source: <a href="/usx/{b}.usx">{b}.usx</a> (USX 3.1).', fabs(prev, nxt)))
        p = OUT / b / f"{n}.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(parts), encoding="utf-8")
        pages += 1
    # /read and /read/{BOOK} index pages are retired (Kevin 14 Nov 9:51 PM): they 301 to the
    # first chapter via Cloudflare Pages _redirects. Books are listed explicitly so assets
    # such as /read/reader.css are never caught by a placeholder rule.
    old = OUT / "index.html"
    if old.exists():
        old.unlink()
    rules = ["# Generated by tools/build_reader.py. Retired reader index pages -> first chapter.",
             "/read /read/GEN/1 301", "/read/ /read/GEN/1 301", "/read/index.html /read/GEN/1 301"]
    for b in ORDER:
        first = parsed[b][1][0].n
        rules += [f"/read/{b} /read/{b}/{first} 301", f"/read/{b}/ /read/{b}/{first} 301"]
    (ROOT / "_redirects").write_text("\n".join(rules) + "\n", encoding="utf-8")
    print(f"wrote {pages} pages to {OUT}; unknown USX elements: {sorted(unknown) or 'none'}")


if __name__ == "__main__":
    build()
