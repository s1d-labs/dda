"""Weekly change watch for dda.gov.in: new tenders, notices, orders and their files.

A GitHub Actions schedule (.github/workflows/watch.yml) puts one queue item a week into project dda-watch
(seed_watch.py). The hub gives it to a pool worker with an India proxy, which runs this task:

  1. read the first page of every paged listing (tenders, notices, circulars, orders, ...) and the home page:
     about 120 requests;
  2. compare every page and file link with the known scope (seeds.json in this repo);
  3. fetch and store each new page, and download and store each new file (capped per week);
  4. store one summary record 'watch-<week>' with the counts and the new URLs.

New pages and files are stored in project dda-watch with the same record shape as dda-pages / dda-docs, so
build_db.py reads them with the rest. A discovery run on the box (discover.py --resume) and Setup make them part
of the main projects later.

    python watch.py --local            # on the box, through the proxy: list what is new, store nothing
"""
import json
import os
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import crawl
import ddatls

HERE = os.path.dirname(os.path.abspath(__file__))
MAX_NEW_PAGES = 150
MAX_NEW_DOCS = 400


def known_scope(path=os.path.join(HERE, "seeds.json")):
    """Canonical URLs of the known pages and documents, and the listings to read (the first page of each)."""
    s = json.load(open(path))
    pages = {crawl.canon_url(u) for u in s.get("pages", [])}
    docs = {crawl.canon_url(u) for u in s.get("documents", [])}
    listings = {crawl.canon_url("https://dda.gov.in/")}
    for u in pages:
        p = urlparse(u)
        if "page" in parse_qs(p.query):
            listings.add(p._replace(query="").geturl())
    return pages, docs, sorted(listings)


def new_links(parsed, known_pages, known_docs):
    """Pure: the page and document links of parsed listing pages that are not in the known scope."""
    new_p, new_d = set(), set()
    for d in parsed:
        for u in d.get("page_links", []):
            c = crawl.canon_url(u)
            if c not in known_pages and not re.search(r"[?&]page=\d", c):
                new_p.add(c)
        for u in d.get("documents", []):
            c = crawl.canon_url(u)
            if c not in known_docs:
                new_d.add(c)
    return sorted(new_p), sorted(new_d)


def run_watch(hub, session, week, local=False):
    known_pages, known_docs, listings = known_scope()
    parsed, errors = [], 0
    for url in listings:
        r, status = crawl.fetch(hub, session, url)
        body = crawl.read_body(hub, r) if r is not None else None
        if body is None:
            errors += 1
            continue
        r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
        parsed.append(crawl.parse(r.text, r.url))
        time.sleep(0.5)
    new_p, new_d = new_links(parsed, known_pages, known_docs)
    stored_p = stored_d = 0
    if not local:
        for url in new_p[:MAX_NEW_PAGES]:
            r, status = crawl.fetch(hub, session, url)
            body = crawl.read_body(hub, r) if r is not None else None
            if body is not None and "html" in r.headers.get("Content-Type", "html").lower():
                d = crawl.store_page(hub, url, r, body)
                d["watch_week"] = week
                stored_p += 1
            time.sleep(0.5)
        for url in new_d[:MAX_NEW_DOCS]:
            r, status = crawl.fetch(hub, session, url)
            content = crawl.read_body(hub, r) if r is not None else None
            if content is not None:
                crawl.store_document(hub, url, r, content, watch_week=week)
                stored_d += 1
            time.sleep(0.5)
    summary = {"type": "watch", "week": week, "listings_read": len(parsed), "listing_errors": errors,
               "new_pages": len(new_p), "new_documents": len(new_d), "stored_pages": stored_p,
               "stored_documents": stored_d, "new_page_urls": new_p[:500], "new_document_urls": new_d[:500],
               "fetched_at": int(time.time())}
    if not local:
        hub.record(f"watch-{week}", summary)
    return summary


def main():
    from scrape_hub_client import HubClient
    hub = HubClient(crawl.PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                    total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1")))
    session = ddatls.make_session()
    try:
        while time.time() < crawl.DEADLINE:
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            s = run_watch(hub, session, item["payload"].get("week", item["key"]))
            if s["listings_read"] == 0:
                hub.complete([item["key"]], "failed", error="no listing page loaded")
            else:
                hub.complete([item["key"]], "done", fetched=1 + s["stored_pages"] + s["stored_documents"])
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


class _NoHub:
    def metric(self, *a, **k): pass
    def error(self): pass
    def block(self): pass


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        s = run_watch(_NoHub(), ddatls.make_session(), time.strftime("%G-W%V"), local=True)
        print(json.dumps({k: v for k, v in s.items() if not k.endswith("_urls")}, indent=1))
        print("new pages:", s["new_page_urls"][:20])
        print("new documents:", s["new_document_urls"][:20])
    else:
        main()
