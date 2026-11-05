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
from urllib.parse import quote, unquote, urljoin, urlparse, urldefrag, urlsplit, urlunsplit

import requests

import ddatls

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "dda-site")
DEADLINE = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 120
HOST = "dda.gov.in"

DOC_EXT = ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar",
           "csv", "rtf", "txt", "odt", "ods", "kmz", "kml", "apk", "exe", "tif", "tiff", "dwg")
GONE = (404, 410)          # a broken link on the site: record it once, do not retry it
GIVE_UP_AFTER = 10         # attempts; then a file the server refuses (403) or always cuts off is recorded, not retried
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
DATE_RX = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.] ?(\d{2,4})\b")


def _strip(fragment):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(fragment or ""))).strip()


def canon_url(url):
    """One spelling per resource on the site: https, no www, no '//' in the path, one percent-encoding
    (a space and %20 are the same file), no fragment. Other hosts are only stripped of the fragment."""
    url, _ = urldefrag((url or "").strip())
    p = urlsplit(url)                        # urlsplit: a ';' stays in the path (urlparse drops it)
    host = p.netloc.lower()
    if host.removeprefix("www.") != HOST:
        return url
    path = re.sub(r"/{2,}", "/", p.path) or "/"
    path = quote(unquote(path), safe="/-._~()!*',;:@&=+$")
    return urlunsplit(("https", HOST, path, p.query, ""))


def norm_url(url, base):
    """An href as found in the HTML ('&amp;' is '&') -> canonical absolute URL."""
    return canon_url(urljoin(base, unescape((url or "").strip())))


def classify(url):
    p = urlsplit(url)
    ext = (re.search(r"\.([a-z0-9]{1,6})$", p.path.lower()) or [None, ""])[1] if "." in p.path else ""
    if p.netloc.lower() not in (HOST, "www." + HOST):
        return "external"
    if ext in DOC_EXT:
        return "document"
    if ext in ASSET_EXT:
        return "asset"
    return "page"


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_NAMED_RX = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[-/. ]+([A-Za-z]{3,9})[-/., ]+(\d{2,4})\b")


def _year(y):
    """4-digit year; a 2-digit year is 19yy or 20yy, whichever is not in the future."""
    two_digit = len(str(y)) <= 2
    y = int(y)
    if two_digit:
        y += 2000 if y <= (time.gmtime().tm_year % 100) + 1 else 1900
    return y


def iso_date(text):
    """First d-m-y date in the text (12-03-2024, 24.04.1965, 20-January-2021, 5 Mar 24) as YYYY-MM-DD.
    Years outside 1900..next year are rejected (they are serial numbers, not dates)."""
    text = text or ""
    found = []
    m = DATE_RX.search(text)
    if m:
        found.append((m.start(), m.group(1), m.group(2), m.group(3)))
    n = DATE_NAMED_RX.search(text)
    if n and n.group(2)[:3].lower() in MONTHS:
        found.append((n.start(), n.group(1), MONTHS[n.group(2)[:3].lower()], n.group(3)))
    for _, d, mth, y in sorted(found):
        try:
            d, mth, y = int(d), int(mth), _year(y)
        except ValueError:
            continue
        if 1 <= d <= 31 and 1 <= mth <= 12 and 1900 <= y <= time.gmtime().tm_year + 1:
            return f"{y:04d}-{mth:02d}-{d:02d}"
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


TABLE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.I | re.S)
CELL = re.compile(r"<(t[dh])\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
MAX_TABLE_ROWS = 5000


def extract_tables(html, base):
    """Every content table that is not a Drupal view (those are in `rows`): header cells, then one
    list of cell texts per row, plus the document links of each row. Pages such as
    /delineated-boundary keep 1,700 colonies in one plain table."""
    tables = []
    for body in TABLE.findall(html):
        if "views-field" in body:
            continue
        headers, rows, links = [], [], []
        for tr in TR.findall(body):
            cells = CELL.findall(tr)
            if not cells:
                continue
            texts = [_strip(c)[:500] for _, c in cells]
            if not any(texts):
                continue
            if not rows and not headers and (all(t.lower() == "th" for t, _ in cells)
                                             or not re.search(r"\d", " ".join(texts[:2]))):
                headers = texts
                continue
            docs = [u for u in (norm_url(h, base) for h in A_HREF.findall(tr)) if classify(u) == "document"]
            rows.append(texts)
            links.append(docs)
            if len(rows) >= MAX_TABLE_ROWS:
                break
        if rows:
            tables.append({"headers": headers, "rows": rows, "documents": links})
    return tables


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
        "tables": extract_tables(html, url),
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
    """GET (or HEAD) one URL. Returns (response, status): response is None unless the status is 200;
    status is None on a connection error or timeout."""
    t = time.time()
    try:
        r = (session.head if head else session.get)(
            url, timeout=45, verify=ddatls.ca_bundle(), allow_redirects=True, stream=not head)
    except requests.RequestException:
        hub.metric("http_error")
        hub.error()
        return None, None
    hub.metric("n_http")
    hub.metric("t_http_s", time.time() - t)
    if r.status_code != 200:
        hub.metric(f"http_{r.status_code}")
        if r.status_code in (403, 429, 503):
            hub.block()
        r.close()
        return None, r.status_code
    return r, 200


def read_body(hub, r):
    """Read a streamed body. A dropped connection mid-file returns None (counted as http_error)
    instead of raising, so one bad download cannot crash the worker."""
    try:
        return r.content
    except (requests.RequestException, OSError):
        hub.metric("http_error")
        hub.error()
        return None
    finally:
        r.close()


def broken_link(hub, item, url, status):
    """The site answers 404/410: store a small record that says so and finish the item,
    so the hub does not retry a link that will never load."""
    hub.record(record_id(url), {"url": url, "type": item["payload"].get("type", "page"),
                                "broken": True, "status": status, "fetched_at": int(time.time())})
    hub.metric("broken_links")
    hub.complete([item["key"]], "done", fetched=0)


def do_page(hub, session, item):
    url = item["payload"]["url"]
    r, status = fetch(hub, session, url)
    if status in GONE:
        return broken_link(hub, item, url, status)
    body_bytes = read_body(hub, r) if r is not None else None
    if body_bytes is None:
        hub.complete([item["key"]], "failed", error=f"page did not load (HTTP {status})" if status else "page did not load")
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
    r, status = fetch(hub, session, url)
    if status in GONE:
        hub.failure("broken-link", item["key"], f"HTTP {status}", url=url)
        return broken_link(hub, item, url, status)
    content = read_body(hub, r) if r is not None else None
    if content is None:
        why = f"HTTP {status}" if status else "connection error or timeout"
        if status == 200:
            why = "connection cut during the transfer"
        hub.failure("document", item["key"], f"download failed: {why}", url=url)
        if item.get("attempts", 0) >= GIVE_UP_AFTER and status in (200, 403):
            # dda.gov.in cuts some files at the same byte on every try, and refuses a few odd links (/.pdf)
            # with 403. After GIVE_UP_AFTER tries, record that and stop: each retry costs a runner job.
            hub.record(record_id(url), {"url": url, "type": "document", "unretrievable": True, "status": status,
                                        "reason": why, "attempts": item.get("attempts"), "fetched_at": int(time.time())})
            hub.metric("unretrievable")
            hub.complete([item["key"]], "done", fetched=0)
            return
        hub.complete([item["key"]], "failed", error=f"document did not load ({why})")
        return
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
