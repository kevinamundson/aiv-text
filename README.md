# Amundson Interpretive Version (AIV): text files

Source for https://aivbible.kevinamundson.me/, served by Cloudflare Pages.

- `usx/{BOOK}.usx`: one USX file per book, served as `application/xml` with `Access-Control-Allow-Origin: *`
- `metadata.json`: translation metadata
- `books.json`: list of the 66 books
- `manifest.json`: export manifest with a sha256 per USX file
- `scripts/sync_from_ezra.sh`: copy a new USX export in byte-for-byte and check sha256
- `scripts/verify_live.py`: fetch every live USX file and check sha256 and headers
- `_headers`: Cloudflare Pages response headers
- `read/`: human-readable reader generated from the USX (`/read/{BOOK}/{N}`; `/read` and `/read/{BOOK}` 301 to the first chapter via the generated `_redirects`). Do not edit the generated pages or `read/nav-data.js` by hand; `read/reader.css` and `read/reader.js` (book panel, search, keyboard chapter navigation) are hand-written.
- `tools/sty2css.py`: generates `read/usfm.css` from the Paratext default stylesheets (`usfm3_1.sty`, fallback `usfm.sty` 3.0.11), pinned by commit and sha256
- `tools/build_reader.py`: builds `read/` from `usx/*.usx` (text rendered exactly as in the USX)
- `tools/verify_reader.py`: checks every chapter page against the USX text and notes

After any USX change, run `python3 tools/sty2css.py && python3 tools/build_reader.py && python3 tools/verify_reader.py` and commit `read/` with the USX.

The AIV is a work in progress and is not finished.

Licensed under CC BY 4.0. See [LICENSE](LICENSE).
