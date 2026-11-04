"""The `crawl` task for the dda.gov.in family (see scrape.json).

Each queue item is one URL with a type:
  {"url": "https://dda.gov.in/whats-new", "type": "page"}      -> fetch HTML, extract structured data
  {"url": "https://dda.gov.in/sites/.../x.pdf", "type": "doc"} -> download the file, store it in the bucket

The queue is seeded from seeds.json (built by discover.py). Run one page without the hub:

    myproxy run python crawl.py --local https://dda.gov.in/whats-new
    myproxy run python crawl.py --local https://dda.gov.in/sites/default/files/2025-07/pio_list_2025.pdf

Records (one per item) go to the hub. Raw HTML and documents go to the family bucket through
hub.upload_many (signed, no keys here). Metrics (n_http, t_http_s, http_<code>, http_error)
drive the hub's politeness. Re-running upserts the same record ids, so there are no duplicates.
"""
import gzip
import hashlib
import json
import os
import re
import sys
import time
from html import unescape
from urllib.parse import urljoin, urlparse, urldefrag

import requests

import ddatls

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "dda-site")
DEADLINE = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 120
HOST = "dda.gov.in"

DOC_EXT = ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar",
           "csv", "rtf", "txt", "odt", "ods")
ASSET_EXT = ("css", "js", "ico", "png", "jpg", "jpeg", "gif", "svg", "webp",
             "woff", "woff2", "ttf", "eot", "mp4", "mp3")

A_HREF = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\']', re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
H1 = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.I | re.S)
META_DESC = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', re.I)
BREADCRUMB = re.compile(r'<nav[^>]*breadcrumb[^>]*>(.*?)</nav>', re.I | re.S)
LI_OR_A = re.compile(r"<(?:li|a)\b[^>]*>(.*?)</(?:li|a)>", re.I | re.S)
# Drupal view table rows and the published-date / title cells
TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
TD = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
PUB_DATE_CELL = re.compile(r'views-field-field-published-date[^>]*>(.*?)</td>', re.I | re.S)
DATE_RX = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b")


def _strip(fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(fragment or ""))).strip()


def norm_url(url, base):
    url = urljoin(base, (url or "").strip())
    url, _ = urldefrag(url)
    return url


def classify(url):
    p = urlparse(url)
    ext = (re.search(r"\.([a-z0-9]{1,6})$", p.path.lower()) or [None, ""])[1] if "." in p.path else ""
    if p.netloc.lower() not in (HOST, "www." + HOST):
        return "external"
    if ext in DOC_EXT:
        return "document"
    if ext in ASSET_EXT:
        return "asset"
    return "page"


def iso_date(text):
    m = DATE_RX.search(text or "")
    if not m:
        return None
    d, mth, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    try:
        d, mth = int(d), int(mth)
        if 1 <= d <= 31 and 1 <= mth <= 12:
            return f"{int(y):04d}-{mth:02d}-{d:02d}"
    except ValueError:
        pass
    return None


def category_from(html, url):
    m = BREADCRUMB.search(html)
    if m:
        crumbs = [_strip(x) for x in LI_OR_A.findall(m.group(1))]
        crumbs = [c for c in crumbs if c and c.lower() != "home"]
        if crumbs:
            return crumbs[-1][:120]
    seg = urlparse(url).path.strip("/").split("/")[0]
    return (seg.replace("-", " ").replace("_", " ").title() or "Home")[:120]


def extract_rows(html, base):
    """Structured rows from a Drupal view table: title, date, and document links."""
    rows = []
    for tr in TR.findall(html):
        if "views-field" not in tr:
            continue
        if "<th" in tr.lower() and "<td" not in tr.lower():
            continue                                    # skip the table header row
        cells = TD.findall(tr)
        if not cells:
            continue
        text = _strip(tr)
        date = None
        pd = PUB_DATE_CELL.search(tr)
        if pd:
            date = iso_date(_strip(pd.group(1))) or _strip(pd.group(1)) or None
        else:
            date = iso_date(text)
        docs = []
        for href in A_HREF.findall(tr):
            u = norm_url(href, base)
            if classify(u) == "document":
                docs.append(u)
        title = _strip(re.sub(r"<td[^>]*field-published-date.*?</td>", " ", tr, flags=re.I | re.S))
        rows.append({"text": title[:300], "date": date, "documents": docs})
    return rows


def parse(html, url="https://dda.gov.in/"):
    """Pure: structured data from one HTML page. Tested on saved pages in tests/."""
    title = _strip(TITLE.search(html).group(1)) if TITLE.search(html) else ""
    title = re.sub(r"\s*\|\s*.*$", "", title) or (_strip(H1.search(html).group(1)) if H1.search(html) else "")
    desc = _strip(META_DESC.search(html).group(1)) if META_DESC.search(html) else ""
    pages, docs, external = set(), set(), set()
    for href in A_HREF.findall(html):
        u = norm_url(href, url)
        if not u.startswith("http"):
            continue
        k = classify(u)
        if k == "page":
            pages.add(u)
        elif k == "document":
            docs.add(u)
        elif k == "external":
            external.add(u)
    rows = extract_rows(html, url)
    dates = sorted({r["date"] for r in rows if r.get("date") and re.match(r"\d{4}-", r["date"] or "")})
    return {
        "url": url,
        "type": "page",
        "title": title[:300],
        "category": category_from(html, url),
        "description": desc[:500],
        "rows": rows,
        "dates": dates,
        "documents": sorted(docs),
        "page_links": sorted(pages),
        "external_links": sorted(external),
        "n_documents": len(docs),
        "n_page_links": len(pages),
    }


def record_id(url):
    """Stable, unique, valid id for a URL (keeps the query; hashes to stay short)."""
    u = urldefrag(url)[0]
    return hashlib.sha1(u.encode()).hexdigest()[:20]


def bucket_path(url, prefix):
    """Keep the site path under <prefix>/, with each segment sanitised to [A-Za-z0-9._-]."""
    p = urlparse(url)
    segs = [re.sub(r"[^A-Za-z0-9._-]", "_", s) for s in p.path.strip("/").split("/") if s]
    if not segs:
        segs = ["index"]
    path = "/".join(segs)
    if p.query:
        path += "_" + re.sub(r"[^A-Za-z0-9._-]", "_", p.query)
    return f"{prefix}/{path}"


# ---------------------------------------------------------------- fetching

def fetch(hub, session, url, head=False):
    t = time.time()
    try:
        r = (session.head if head else session.get)(
            url, timeout=45, verify=ddatls.ca_bundle(), allow_redirects=True, stream=not head)
    except requests.RequestException:
        hub.metric("http_error")
        hub.error()
        return None
    hub.metric("n_http")
    hub.metric("t_http_s", time.time() - t)
    if r.status_code != 200:
        hub.metric(f"http_{r.status_code}")
        if r.status_code in (403, 429, 503):
            hub.block()
        return None
    return r


def do_page(hub, session, item):
    url = item["payload"]["url"]
    r = fetch(hub, session, url)
    if r is None:
        hub.complete([item["key"]], "failed", error="page did not load")
        return
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    body = r.text
    data = parse(body, r.url)
    data["fetched_at"] = int(time.time())
    data["content_sha256"] = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()
    try:
        hub.upload_many([(bucket_path(url, "pages") + ".html.gz",
                          gzip.compress(body.encode("utf-8", "replace")), "application/gzip")])
    except Exception as e:
        data["upload_error"] = str(e)[:120]
    hub.record(record_id(url), data)
    hub.complete([item["key"]], "done", fetched=1)


def do_doc(hub, session, item):
    url = item["payload"]["url"]
    r = fetch(hub, session, url)
    if r is None:
        hub.failure("document", item["key"], "download failed", url=url)
        hub.complete([item["key"]], "failed", error="document did not load")
        return
    content = r.content
    sha = hashlib.sha256(content).hexdigest()
    ext = (re.search(r"\.([a-z0-9]{1,6})$", urlparse(url).path.lower()) or [None, ""])[1]
    data = {
        "url": url,
        "type": "document",
        "filename": urlparse(url).path.rsplit("/", 1)[-1][:200],
        "ext": ext,
        "bytes": len(content),
        "sha256": sha,
        "content_type": r.headers.get("Content-Type", ""),
        "referrer": item["payload"].get("referrer", ""),
        "category": item["payload"].get("category", ""),
        "fetched_at": int(time.time()),
    }
    try:
        hub.upload_many([(bucket_path(url, "docs"), content,
                          r.headers.get("Content-Type", "application/octet-stream").split(";")[0])])
    except Exception as e:
        data["upload_error"] = str(e)[:120]
    hub.record(record_id(url), data)
    hub.complete([item["key"]], "done", fetched=1)


def main():
    from scrape_hub_client import HubClient
    hub = HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")),
                    total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1")))
    session = ddatls.make_session()
    try:
        while time.time() < DEADLINE:
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            kind = item["payload"].get("type", "page")
            if kind == "doc" or kind == "document":
                do_doc(hub, session, item)
            else:
                do_page(hub, session, item)
            time.sleep(max(0.3, hub.settings.get("delay_ms", 0) / 1000))
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


# ---------------------------------------------------------------- local test

def local(url):
    session = ddatls.make_session()
    r = session.get(url, timeout=45, verify=ddatls.ca_bundle(), allow_redirects=True)
    ctype = r.headers.get("Content-Type", "")
    if "html" in ctype.lower():
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        data = parse(r.text, r.url)
        data["rows"] = data["rows"][:5]
        data["page_links"] = data["page_links"][:10]
        data["external_links"] = data["external_links"][:10]
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"\n[{r.status_code}] {len(r.content)} bytes | {data['n_documents']} docs | "
              f"{data['n_page_links']} page links | {len(parse(r.text, r.url)['rows'])} rows", file=sys.stderr)
    else:
        print(json.dumps({"url": url, "type": "document", "content_type": ctype,
                          "bytes": len(r.content), "sha256": hashlib.sha256(r.content).hexdigest(),
                          "bucket_path": bucket_path(url, "docs")}, indent=2))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        local(sys.argv[2] if len(sys.argv) > 2 else "https://dda.gov.in/")
    else:
        main()
