#!/usr/bin/env python3
"""Fetch every /usx file from a host with plain urllib (no browser UA) and compare sha256 to manifest.json."""
import hashlib, json, sys, urllib.request
base = (sys.argv[1] if len(sys.argv) > 1 else "https://aivbible.kevinamundson.me").rstrip("/")
manifest = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "manifest.json"))
bad = []
for b in manifest["books"]:
    with urllib.request.urlopen(f"{base}/{b['file']}") as r:
        body, ctype, acao = r.read(), r.headers.get("Content-Type"), r.headers.get("Access-Control-Allow-Origin")
    ok = hashlib.sha256(body).hexdigest() == b["sha256"] and ctype.startswith("application/xml") and acao == "*"
    if not ok: bad.append((b["usfm"], ctype, acao))
print(f"{base}: {len(manifest['books']) - len(bad)}/{len(manifest['books'])} match sha256 + application/xml + ACAO *; bad={bad}")
sys.exit(1 if bad else 0)
