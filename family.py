"""What the dda.gov.in family scrapes.

Two projects, both on host dda.gov.in, reached through the hub's India proxy (the
site answers only from India and needs legacy TLS, handled in ddatls.py):

  dda-pages  -- every public HTML page (structured data: title, category, dates, view rows, links)
  dda-docs   -- every linked document (pdf, doc, xls, zip, ...) stored in the bucket

The queue items come from seeds.json, built by discover.py:

    myproxy run python discover.py        # refresh seeds.json
    # then run the Setup workflow (Actions -> setup) to apply this to the hub

seeds.json is optional at import time; without it the projects register with an
empty queue, which a later discover + Setup fills (seed_queue keeps old keys).
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
FAMILY = json.loads((HERE / "scrape.json").read_text())["family"]
TARGET = "dda.gov.in"
SITE = "https://dda.gov.in/"

# No health-check probe. dda.gov.in needs legacy TLS renegotiation (see ddatls.py),
# which the hub's prober does not do, so a probe here would stay red and hold all
# work. The crawl task handles the TLS itself and reports errors for retry, so the
# project runs without a probe gating it.
PROBE = ""   # explicit empty clears the probe on the hub (None would leave the old one)


def _seeds():
    p = HERE / "seeds.json"
    if not p.exists():
        return {"pages": [], "documents": [], "page_meta": {}}
    return json.loads(p.read_text())


def _record_key(url):
    import hashlib
    return hashlib.sha1(url.encode()).hexdigest()[:20]


def _unique(urls):
    """Drop a second spelling of one URL (http vs https, space vs %20, '//' in the path).
    The first spelling seen keeps its key, so the queue items on the hub do not change."""
    from crawl import canon_url
    seen, out = set(), []
    for u in sorted(urls, key=lambda u: (not u.startswith("https://"), "%" not in u, u)):
        c = canon_url(u)
        if c not in seen:
            seen.add(c)
            out.append(u)
    return sorted(out)


_s = _seeds()
_meta = _s.get("page_meta", {})

PAGE_ITEMS = [
    {"key": "p-" + _record_key(u),
     "payload": {"url": u, "type": "page",
                 "expected": 1 + (_meta.get(u, {}).get("n_docs", 0))}}
    for u in _unique(_s.get("pages", []))
]

DOC_ITEMS = [
    {"key": "d-" + _record_key(u), "payload": {"url": u, "type": "doc", "expected": 1}}
    for u in _unique(_s.get("documents", []))
]

PROJECTS = [
    {
        "name": f"{FAMILY}-pages",
        "title": "DDA public pages",
        "task": "crawl",
        "target": TARGET,
        "env": {"SITE": SITE},
        "probe": PROBE,
        "proxy": "IN",
        "max_workers": 4,          # while documents are paused, give pages all 4 India proxies
        "unit_label": "page", "record_label": "page",
        "items": PAGE_ITEMS,
    },
    {
        "name": f"{FAMILY}-docs",
        "title": "DDA documents (PDF, DOC, XLS, ...)",
        "task": "crawl",
        "target": TARGET,
        "env": {"SITE": SITE},
        "probe": PROBE,
        "proxy": "IN",
        "max_workers": 4,          # pages are scraped; documents now use all 4 India proxies
        "pool": False,             # paused while the 399 repaired pages are scraped first
        "unit_label": "file", "record_label": "document",
        "items": DOC_ITEMS,
    },
]

PROBES = []  # no probe: see the note in family.py
