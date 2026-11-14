#!/usr/bin/env python3
"""Build the human-readable AIV reader (read/) from usx/*.usx.

Renders exactly what is in the USX: every publishable paragraph, character
style and footnote, in source order, with no change to wording. Styles come
from read/usfm.css, which tools/sty2css.py generates from the Paratext default
stylesheets. Layout and chrome live in read/reader.css (hand-written).

Output (served by Cloudflare Pages with pretty URLs):
  read/index.html            book list          -> /read/
  read/{BOOK}/index.html     chapter list       -> /read/GEN/
  read/{BOOK}/{N}.html       one chapter        -> /read/GEN/1
The raw USX, manifest.json, books.json and metadata.json are left untouched.

Usage: python3 tools/sty2css.py && python3 tools/build_reader.py && python3 tools/verify_reader.py
"""
import html, json, pathlib, shutil, sys
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


def para_html(st, body):
    kind = "apparatus" if is_apparatus(st) else "scripture"
    tag = HEADING_TAG.get(st, "p")
    return f'<{tag} class="usfm-{attr(st)} {kind}">{body}</{tag}>'


HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Vollkorn:ital,wght@0,400..900;1,400..900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/read/usfm.css">
<link rel="stylesheet" href="/read/reader.css">
{extra}</head>
<body>
<header class="site"><a class="home" href="/read/">Amundson Interpretive Version</a> <span class="status">DRAFT</span></header>
"""


def foot(source_links):
    return f"""<footer class="site">
<p class="draft">The AIV is a work in progress. It is not finished, and its wording may change.</p>
<p>Amundson Interpretive Version (AIV), {esc(CREDIT)}.</p>
<p>&copy; 2026 Kevin Amundson. Licensed under <a href="/LICENSE">CC BY 4.0</a>. {source_links}</p>
</footer>
</body>
</html>
"""


def nav(book, name, n, total, prev, nxt):
    p = f'<a rel="prev" href="/read/{prev[0]}/{prev[1]}">&lsaquo; {esc(prev[2])}</a>' if prev else "<span></span>"
    x = f'<a rel="next" href="/read/{nxt[0]}/{nxt[1]}">{esc(nxt[2])} &rsaquo;</a>' if nxt else "<span></span>"
    return (f'<nav class="chap">{p}<a class="up" href="/read/{book}/">{esc(name)} '
            f'&middot; chapters</a>{x}</nav>\n')


def chapter_label(book, n):
    return f"Psalm {n}" if book == "PSA" else f"Chapter {n}"


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
    lab = lambda b, n: (f"Psalm {n}" if b == "PSA" else f"{books[b]} {n}") if len(parsed[b][1]) > 1 else books[b]
    pages = 0
    for i, (b, n) in enumerate(seq):
        intro, chs = parsed[b]
        ch = next(c for c in chs if c.n == n)
        prev = (seq[i - 1][0], seq[i - 1][1], lab(*seq[i - 1])) if i else None
        nxt = (seq[i + 1][0], seq[i + 1][1], lab(*seq[i + 1])) if i + 1 < len(seq) else None
        parts = [HEAD.format(title=f"{esc(lab(b, n))} · AIV (draft)",
                             desc=f"{attr(lab(b, n))} in the Amundson Interpretive Version (AIV), a draft English Bible text.",
                             extra=f'<link rel="alternate" type="application/xml" href="/usx/{b}.usx" title="USX source">\n'),
                 nav(b, books[b], n, len(chs), prev, nxt),
                 f'<main class="text" lang="en" data-book="{b}" data-chapter="{n}">\n']
        if n == chs[0].n:
            parts += [para_html(s, body) + "\n" for s, body in intro.paras]
        parts.append(f'<h2 class="usfm-c chrome">{esc(chapter_label(b, n))}</h2>\n')
        parts += [para_html(s, body) + "\n" for s, body in ch.paras]
        parts.append("</main>\n")
        if ch.notes:
            parts.append('<section class="notes" aria-label="Notes">\n<h2 class="chrome">Notes</h2>\n<ol>\n')
            for k, mark, st, body in ch.notes:
                parts.append(f'<li id="fn{k + 1}"><a class="fn-back" href="#fnr{k + 1}" '
                             f'aria-label="back to text">{esc(mark)}</a> '
                             f'<span class="usfm-{attr(st)} note-body">{body}</span></li>\n')
            parts.append("</ol>\n</section>\n")
        parts.append(nav(b, books[b], n, len(chs), prev, nxt))
        parts.append(foot(f'Source: <a href="/usx/{b}.usx">{b}.usx</a> (USX 3.1).'))
        p = OUT / b / f"{n}.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(parts), encoding="utf-8")
        pages += 1
    for b in ORDER:
        chs = parsed[b][1]
        grid = "".join(f'<li><a href="/read/{b}/{c.n}">{c.n}</a></li>' for c in chs)
        page = (HEAD.format(title=f"{esc(books[b])} · AIV (draft)",
                            desc=f"Chapters of {attr(books[b])} in the Amundson Interpretive Version (AIV).", extra="")
                + f'<main class="index"><h1>{esc(books[b])}</h1>\n<ul class="chapters">{grid}</ul>\n'
                + f'<p class="dev">Source file: <a href="/usx/{b}.usx">/usx/{b}.usx</a> (USX 3.1)</p>\n'
                + '<p><a href="/read/">&lsaquo; All books</a></p></main>\n'
                + foot(""))
        (OUT / b / "index.html").write_text(page, encoding="utf-8")
        pages += 1
    groups, last_t = [], None
    for t, sub, s in GROUPS:
        if t != last_t:
            groups.append(f"<h2>{esc(t)}</h2>"); last_t = t
        if sub:
            groups.append(f"<h3>{esc(sub)}</h3>")
        items = "".join(f'<li><a class="book" href="/read/{b}/">{esc(books[b])}</a> '
                        f'<span class="usxp">(<a class="usx" href="/usx/{b}.usx" title="USX source file">{b}.usx</a>)</span></li>'
                        for b in s.split())
        groups.append(f'<ul class="books">{items}</ul>')
    landing = (HEAD.format(title="Read the AIV (draft)",
                           desc="Read the Amundson Interpretive Version (AIV), a draft English Bible text, book by book.",
                           extra="")
               + '<main class="index">\n<h1>Read the Bible</h1>\n'
               + '<p class="draft">This is a draft. The text is under active revision and may change.</p>\n'
               + "\n".join(groups) + "\n"
               + '<section class="key"><h2>How to read this page</h2><ul>'
               + '<li><span class="usfm-add">Italic words</span> are supplied by the translator for sense in English.</li>'
               + '<li><span class="apparatus">Headings, parallel references</span> and the lettered notes<span class="fn-call"><sup>a</sup></span> '
               + 'are editorial aids. They are not part of the Scripture text.</li></ul></section>\n'
               + '<section class="dev" id="data"><h2>For developers and Scripture apps</h2><ul>'
               + '<li>USX 3.1 files, one per book: <code>/usx/{BOOK}.usx</code> (for example <a href="/usx/GEN.usx">/usx/GEN.usx</a>)</li>'
               + '<li><a href="/manifest.json">manifest.json</a>: book list, counts and sha256 per USX file</li>'
               + '<li><a href="/books.json">books.json</a>: the 66 books and their USX paths</li>'
               + '<li><a href="/metadata.json">metadata.json</a>: translation metadata and licence</li>'
               + '</ul><p>All of these are served with <code>Access-Control-Allow-Origin: *</code>. '
               + 'Styling follows the Paratext default USFM stylesheet (<a href="/read/usfm.css">usfm.css</a>).</p></section>\n'
               + "</main>\n" + foot(""))
    (OUT / "index.html").write_text(landing, encoding="utf-8")
    pages += 1
    print(f"wrote {pages} pages to {OUT}; unknown USX elements: {sorted(unknown) or 'none'}")


if __name__ == "__main__":
    build()
