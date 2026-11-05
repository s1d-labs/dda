"""Discover every public page and document on dda.gov.in.

A breadth-first crawl of the site. It follows internal HTML pages, records every
document link (pdf, doc, xls, ...), and notes external links. It writes seeds.json,
which family.py reads to seed the pool queue, and prints a scope summary.

Run it on the box through the India proxy (dda.gov.in answers only from India):

    myproxy run python discover.py            # full crawl
    myproxy run python discover.py --max 50   # quick sample

Output: seeds.json  { "pages": [...], "documents": [...], "external": {...}, "stats": {...} }
It is resumable in the sense that re-running refreshes the list; seed_queue keeps old keys.
"""
import argparse
import json
import os
import re
import signal
import sys
import time
from collections import deque, Counter
from html import unescape
from urllib.parse import urljoin, urlparse, urldefrag, urlsplit

import ddatls

HOST = "dda.gov.in"
BASE = "https://dda.gov.in/"
DOC_EXT = ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar",
           "csv", "rtf", "txt", "odt", "ods", "kmz", "kml", "apk", "exe", "tif", "tiff", "dwg")
ASSET_EXT = ("css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp",
             "woff", "woff2", "ttf", "eot", "mp4", "mp3", "json", "xml")
SEEDS_PATH = "seeds.json"

A_HREF = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\']', re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def norm(url):
    """Absolute, fragment-free, canonical URL (https, one encoding, no '//').
    Keeps the query (Drupal paging uses ?page=N). http:// and https:// spellings of one page
    were crawled twice before this (221 pages); canon_url makes them one."""
    from crawl import canon_url
    return canon_url(url)


def classify(url):
    p = urlsplit(url)
    host = p.netloc.lower()
    path = p.path.lower()
    m = re.search(r"\.([a-z0-9]{1,6})$", path)
    ext = m.group(1) if m else ""
    if host not in (HOST, "www." + HOST):
        return "external", ext
    if ext in DOC_EXT:
        return "document", ext
    if ext in ASSET_EXT:
        return "asset", ext
    return "page", ext


def links_on(page, base_url):
    for href in A_HREF.findall(page):
        href = unescape(href.strip())          # '&amp;' in an href is '&' (157 file links were lost without this)
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        yield norm(urljoin(base_url, href))


def pager_pages(link):
    """Drupal shows only a window of pager links. A link to ?page=N means pages 1..N exist; queue them
    all, so one timeout in the chain cannot hide the rest of a listing (it hid 395 pages once)."""
    p = urlparse(link)
    m = re.fullmatch(r"page=(\d+)", p.query or "")
    if not m:
        return []
    return [p._replace(query=f"page={n}").geturl() for n in range(1, int(m.group(1)) + 1)]


def page_title(page):
    m = TITLE.search(page)
    if not m:
        return ""
    return re.sub(r"\s+", " ", unescape(m.group(1))).strip()[:300]


def _snapshot(pages, documents, external, errors, frontier, fetched, t0):
    return {
        "pages": sorted(pages),
        "page_meta": pages,
        "documents": sorted(documents),
        "external": dict(external.most_common()),
        "errors": errors,
        "frontier": list(frontier),
        "stats": {
            "pages_fetched": fetched,
            "pages_total": len(pages),
            "pages_queued_unreached": len(frontier),
            "documents": len(documents),
            "external_hosts": len(external),
            "errors": len(errors),
            "seconds": round(time.time() - t0, 1),
        },
    }


def _save(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def repair_targets(prev):
    """What a --repair pass fetches again: the first page of every paged listing (its pager shows the
    last page), the pager gaps, the unreached frontier, and error URLs that were '&amp;' links."""
    from crawl import canon_url
    paged = {}
    for u in prev.get("pages", []):
        p = urlparse(canon_url(u))
        m = re.fullmatch(r"page=(\d+)", p.query or "")
        if m:
            paged.setdefault(p._replace(query="").geturl(), set()).add(int(m.group(1)))
    refetch, gaps = [], []
    for base, nums in paged.items():
        refetch.append(base)
        gaps += [f"{base}?page={n}" for n in range(1, max(nums) + 1) if n not in nums]
    fixed = {}
    for u in prev.get("errors", {}):
        if "&amp;" in u or "&amp" in u:
            fixed[u] = canon_url(unescape(u.replace("&amp", "&amp;").replace("&amp;;", "&amp;")))
    return refetch, gaps, fixed


def crawl(max_pages, delay, verbose=True, out=None, resume=False, checkpoint_every=100, repair=False):
    session = ddatls.make_session()
    bundle = ddatls.ca_bundle()
    seen_pages = set()
    frontier = deque()
    documents = {}          # url -> {referrer, ext}
    external = Counter()
    pages = {}              # url -> {title, n_docs}
    errors = {}             # url -> reason
    fetched = 0
    t0 = time.time()

    if resume and out and os.path.exists(out):
        prev = json.load(open(out))
        pages = prev.get("page_meta", {})
        documents = {u: {} for u in prev.get("documents", [])}
        external = Counter(prev.get("external", {}))
        errors = prev.get("errors", {})
        from crawl import canon_url
        for u in prev.get("pages", []):
            seen_pages.add(u)
            seen_pages.add(canon_url(u))
        for u in prev.get("frontier", []):
            if u not in seen_pages:
                seen_pages.add(u)
                frontier.append(u)
        print(f"resumed: {len(pages)} pages done, {len(frontier)} queued, {len(documents)} docs", file=sys.stderr)
        if repair:
            refetch, gaps, fixed = repair_targets(prev)
            for u in [d for d in documents if "&amp;" in d]:        # a document seeded with '&amp;' in it
                documents.pop(u)
                documents.setdefault(canon_url(unescape(u)), {})
            for bad, good in fixed.items():
                errors.pop(bad, None)
                kind, _ = classify(good)
                if kind == "document":
                    documents.setdefault(good, {})
                elif good not in seen_pages:
                    seen_pages.add(good)
                    frontier.append(good)
            for u in gaps:
                if u not in seen_pages:
                    seen_pages.add(u)
                    frontier.append(u)
            frontier.extendleft(reversed(refetch))       # first pages again: their pagers show the last page
            print(f"repair: {len(refetch)} listings, {len(gaps)} pager gaps, {len(fixed)} '&amp;' links, "
                  f"frontier now {len(frontier)}", file=sys.stderr)

    for s in [BASE, BASE + "sitemap"]:
        if s not in seen_pages:
            seen_pages.add(s)
            frontier.append(s)

    stop = {"now": False}

    def _on_signal(signum, frame):
        stop["now"] = True
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    while frontier and fetched < max_pages and not stop["now"]:
        url = frontier.popleft()
        try:
            r = session.get(url, timeout=45, verify=bundle, allow_redirects=True)
        except Exception as e:
            errors[url] = f"{type(e).__name__}: {e}"[:160]
            continue
        fetched += 1
        if r.status_code != 200:
            errors[url] = f"HTTP {r.status_code}"
            continue
        ctype = r.headers.get("Content-Type", "")
        if "html" not in ctype.lower():
            # a page URL that is really a file
            documents.setdefault(url, {"referrer": url, "ctype": ctype})
            continue
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        body = r.text
        n_docs = 0
        for link in links_on(body, r.url):
            kind, ext = classify(link)
            if kind == "page":
                for u in [link] + pager_pages(link):
                    if u not in seen_pages:
                        seen_pages.add(u)
                        frontier.append(u)
            elif kind == "document":
                documents.setdefault(link, {"referrer": url, "ext": ext})
                n_docs += 1
            elif kind == "external":
                external[urlparse(link).netloc.lower()] += 1
        pages[url] = {"title": page_title(body), "n_docs": n_docs}
        if verbose and fetched % 20 == 0:
            print(f"  ...{fetched} pages, frontier {len(frontier)}, docs {len(documents)}", file=sys.stderr)
        if out and fetched % checkpoint_every == 0:
            _save(out, _snapshot(pages, documents, external, errors, frontier, fetched, t0))
        time.sleep(delay)

    state = _snapshot(pages, documents, external, errors, frontier, fetched, t0)
    if out:
        _save(out, state)
        if stop["now"]:
            print("stopped by signal; checkpoint saved", file=sys.stderr)
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=5000, help="max pages to fetch")
    ap.add_argument("--delay", type=float, default=0.7, help="seconds between requests")
    ap.add_argument("--out", default=SEEDS_PATH)
    ap.add_argument("--resume", action="store_true", help="continue from an existing seeds.json")
    ap.add_argument("--checkpoint-every", type=int, default=100)
    ap.add_argument("--repair", action="store_true",
                    help="with --resume: re-read paged listings, fill pager gaps, fix '&amp;' links")
    args = ap.parse_args()
    result = crawl(args.max, args.delay, out=args.out, resume=args.resume,
                   checkpoint_every=args.checkpoint_every, repair=args.repair)
    print(json.dumps(result["stats"], indent=2))
    print("top external hosts:", dict(list(result["external"].items())[:12]))
    doc_ext = Counter()
    for u in result["documents"]:
        m = re.search(r"\.([a-z0-9]{1,6})$", urlparse(u).path.lower())
        doc_ext[m.group(1) if m else "?"] += 1
    print("documents by type:", dict(doc_ext.most_common()))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
