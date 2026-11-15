#!/usr/bin/env python3
"""Check that read/ renders the USX text exactly.

For every chapter: the sequence of (paragraph style, text without notes) and the
list of footnote texts in read/{BOOK}/{N}.html must equal what the USX holds.
Verse numbers, note callers and chrome are excluded on both sides. Also checks
verse and note counts, that no chrome mentions the source translation's name,
and that every chapter has a page."""
import html.parser, pathlib, re, sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_reader import ORDER, publishable  # noqa: E402


def usx_text(el, notes, top=True):
    out = [el.text or ""]
    for c in el:
        if c.tag == "note":
            notes.append(usx_text(c, [], False))
        elif c.tag == "verse":
            pass
        else:
            out.append(usx_text(c, notes, False))
        out.append(c.tail or "")
    return "".join(out)


def from_usx(path):
    chapters, cur, verses = {}, None, 0
    for el in ET.parse(path).getroot():
        if el.tag == "chapter":
            cur = int(el.get("number")) if el.get("sid") else None
            if cur:
                chapters[cur] = ([], [])
            continue
        if el.tag != "para" or not publishable(el.get("style", "")):
            continue
        key = cur if cur else (min(chapters) if chapters else 0)
        paras, notes = chapters.setdefault(key, ([], []))
        paras.append((el.get("style"), usx_text(el, notes)))
        verses += len(el.findall(".//verse[@sid]"))
    if 0 in chapters:  # intro paragraphs print on the first chapter page
        p0, n0 = chapters.pop(0)
        first = min(chapters)
        chapters[first] = (p0 + chapters[first][0], n0 + chapters[first][1])
    return chapters, verses


class Page(html.parser.HTMLParser):
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.paras, self.notes, self.verses, self.cur = [], [], [], 0, None
        self.zone, self.chrome = None, []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        skip = bool({"vn", "fn-call", "fn-back", "chrome"} & set(cls))
        self.stack.append((tag, skip))
        if tag == "main" and "text" in cls:
            self.zone = "text"
        elif tag == "section" and "notes" in cls:
            self.zone = "notes"
        if "usfm-v" in cls:
            self.verses += 1
        if self.zone == "text" and tag in self.BLOCK and not skip:
            style = next(c[5:] for c in cls if c.startswith("usfm-"))
            self.cur = [style, ""]
            self.paras.append(self.cur)
        if self.zone == "notes" and "note-body" in cls:
            self.cur = ["note", ""]
            self.notes.append(self.cur)

    def handle_endtag(self, tag):
        t, _ = self.stack.pop()
        if tag in ("main", "section"):
            self.zone = None
        if tag in self.BLOCK:
            self.cur = None

    def handle_data(self, d):
        if any(s for _, s in self.stack):
            return
        if self.cur is not None and self.zone in ("text", "notes"):
            self.cur[1] += d
        elif self.zone is None:
            self.chrome.append(d)


def main():
    bad, pages, nv, nn = [], 0, 0, 0
    for b in ORDER:
        chapters, verses = from_usx(ROOT / "usx" / f"{b}.usx")
        vpage = 0
        for n, (paras, notes) in chapters.items():
            p = ROOT / "read" / b / f"{n}.html"
            if not p.exists():
                bad.append(f"{b} {n}: no page"); continue
            pg = Page(); pg.feed(p.read_text(encoding="utf-8")); pages += 1
            got = [tuple(x) for x in pg.paras]
            if got != paras:
                for i, (g, w) in enumerate(zip(got, paras)):
                    if g != w:
                        bad.append(f"{b} {n} para {i}: html={g!r} usx={w!r}"); break
                else:
                    bad.append(f"{b} {n}: {len(got)} html paras vs {len(paras)} usx")
            if [x[1] for x in pg.notes] != notes:
                bad.append(f"{b} {n}: notes differ ({len(pg.notes)} html vs {len(notes)} usx)")
            if re.search(r"berean", " ".join(pg.chrome), re.I):
                bad.append(f"{b} {n}: source name in page chrome")
            vpage += pg.verses
            nn += len(notes)
        if vpage != verses:
            bad.append(f"{b}: {vpage} verse numbers in pages vs {verses} in USX")
        nv += verses
    for p in [ROOT / "index.html"]:
        if re.search(r"berean", p.read_text(), re.I):
            bad.append(f"{p}: source name in index chrome")
    print(f"chapters={pages} verses={nv} notes={nn} problems={len(bad)}")
    for x in bad[:40]:
        print("  ", x)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
