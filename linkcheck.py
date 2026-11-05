"""Check the documents the pool could not download: are they broken links on the site (404)?

The pool marks an item failed when a download does not load. This sends one HEAD request per
failed document (gently, through the India proxy) and writes linkcheck.json {url: status}.
build_db.py reads it and marks 404/410 documents as 'broken'.

    myproxy run python linkcheck.py                 # failed documents from the workspace db
    myproxy run python linkcheck.py --db ws_trideep --delay 0.7
"""
import argparse
import json
import os
import subprocess
import time
from collections import Counter

import ddatls


def failed_urls(db):
    out = subprocess.run(["psql", db, "-tAc", "select url from dda.documents where status='failed'"],
                         capture_output=True, text=True, check=True)
    return [u for u in out.stdout.splitlines() if u]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    ap.add_argument("--delay", type=float, default=0.7)
    ap.add_argument("--out", default="linkcheck.json")
    args = ap.parse_args()
    prev = json.load(open(args.out)) if os.path.exists(args.out) else {}
    s = ddatls.make_session(retries=1)
    checked = prev.get("status", {})
    for u in failed_urls(args.db):
        try:
            r = s.head(u, timeout=40, verify=ddatls.ca_bundle(), allow_redirects=True)
            checked[u] = r.status_code
        except Exception as e:      # noqa: BLE001 - a timeout is a result here, not a crash
            checked[u] = type(e).__name__
        time.sleep(args.delay)
    with open(args.out, "w") as f:
        json.dump({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "status": checked},
                  f, indent=0, sort_keys=True)
    print(Counter(checked.values()))


if __name__ == "__main__":
    main()
