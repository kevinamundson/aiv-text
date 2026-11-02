#!/usr/bin/env python3
"""Fetch every /usx file from a host with plain curl (default curl UA, no browser UA)
and check sha256 against manifest.json, plus Content-Type application/xml and ACAO *."""
import hashlib, json, subprocess, sys
base = (sys.argv[1] if len(sys.argv) > 1 else "https://aivbible.kevinamundson.me").rstrip("/")
manifest = json.load(open(sys.argv[2] if len(sys.argv) > 2 else "manifest.json"))
bad = []
for b in manifest["books"]:
    out = subprocess.run(["curl", "-sS", "-D", "/dev/stderr", f"{base}/{b['file']}"], capture_output=True, check=True)
    hdrs = {l.split(":", 1)[0].lower(): l.split(":", 1)[1].strip() for l in out.stderr.decode().splitlines() if ":" in l}
    ok = (hashlib.sha256(out.stdout).hexdigest() == b["sha256"]
          and hdrs.get("content-type", "").startswith("application/xml")
          and hdrs.get("access-control-allow-origin") == "*")
    if not ok: bad.append((b["usfm"], hdrs.get("content-type"), hdrs.get("access-control-allow-origin")))
print(f"{base}: {len(manifest['books']) - len(bad)}/{len(manifest['books'])} match sha256 + application/xml + ACAO *; bad={bad}")
sys.exit(1 if bad else 0)
