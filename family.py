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
import os
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
        # Normally on. To scrape pages first, run Setup with the input docs_pool=false; Setup without it turns
        # documents on again. (Running workers finish their run; only new assignments follow this flag.)
        "pool": os.environ.get("DDA_DOCS_POOL", "true").lower() != "false",
        "unit_label": "file", "record_label": "document",
        "items": DOC_ITEMS,
    },
]

# The two small public portals next to dda.gov.in (portals.py; seeds from `python portals.py discover`).
# They answer from outside India: no proxy, GitHub runners only, one gentle worker each.
def _portal_seeds():
    p = HERE / "data" / "portal_seeds.json"
    return json.loads(p.read_text()) if p.exists() else {"stf_pages": {}, "stf_files": [], "greens_parks": []}


_ps = _portal_seeds()
STF_ITEMS = (
    [{"key": "s-" + _record_key(u), "payload": {"url": u, "type": "stf-page", "section": m.get("section", ""),
                                                 "expected": 1}} for u, m in _ps["stf_pages"].items()]
    + [{"key": "f-" + _record_key(u), "payload": {"url": u, "type": "doc", "expected": 1}} for u in _ps["stf_files"]]
)


def _greens_items():
    from portals import greens_endpoints
    return [{"key": "g-" + _record_key(e), "payload": {"endpoint": e, "type": "api", "expected": 1,
                                                        "park_id": (e.split("parkId=")[1].split("&")[0] if "parkId=" in e else None)}}
            for e in greens_endpoints(_ps["greens_parks"])]


PROJECTS += [
    {
        "name": f"{FAMILY}-stf",
        "title": "DDA Special Task Force: meeting agendas, minutes, notices",
        "task": "portal", "target": "stf.dda.org.in", "env": {"SITE": "https://stf.dda.org.in/"},
        "probe": PROBE, "max_workers": 1, "delay_ms": 800,
        "unit_label": "page or file", "record_label": "record",
        "items": STF_ITEMS,
    },
    {
        "name": f"{FAMILY}-greens",
        "title": "DDA Greens: plantation dashboard, parks, species",
        "task": "portal", "target": "ddagreens.dda.org.in", "env": {"SITE": "https://ddagreens.dda.org.in/"},
        "probe": PROBE, "max_workers": 1, "delay_ms": 800,
        "unit_label": "API call", "record_label": "record",
        "items": _greens_items(),
    },
    {
        # One item a week (seed_watch.py from .github/workflows/watch.yml): new listings, pages and files.
        "name": f"{FAMILY}-watch",
        "title": "DDA weekly change watch (new tenders, notices, orders)",
        "task": "watch", "target": TARGET, "env": {"SITE": SITE},
        "probe": PROBE, "proxy": "IN", "max_workers": 1,
        "unit_label": "weekly check", "record_label": "record",
        "items": [],
    },
]

PROBES = []  # no probe: see the note above (legacy TLS)
