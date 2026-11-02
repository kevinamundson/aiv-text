# Amundson Interpretive Version (AIV): text files

Source for https://aivbible.kevinamundson.me/, served by Cloudflare Pages.

- `usx/{BOOK}.usx`: one USX file per book, served as `application/xml` with `Access-Control-Allow-Origin: *`
- `metadata.json`: translation metadata
- `books.json`: list of the 66 books
- `manifest.json`: export manifest with a sha256 per USX file
- `scripts/sync_from_ezra.sh`: copy a new USX export in byte-for-byte and check sha256
- `scripts/verify_live.py`: fetch every live USX file and check sha256 and headers
- `_headers`: Cloudflare Pages response headers

The AIV is a work in progress and is not finished.

Licensed under CC BY 4.0. See [LICENSE](LICENSE).
