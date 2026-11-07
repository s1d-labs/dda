"""Two small public DDA portals next to dda.gov.in: the Special Task Force (STF) and DDA Greens.

  dda-stf     https://stf.dda.org.in            STF (constituted under a Supreme Court order) against misuse and
                                                encroachment: meeting agendas and minutes (PDF), notices, status pages.
  dda-greens  https://ddagreens.dda.org.in      plantation drive: dashboard, parks, park and species summaries (JSON API).

Both answer from outside India, so the pool runs them on GitHub runners with no proxy. Not scraped (on purpose):
the STF login, the complaint forms, the lists of named officers, and the Greens officer endpoints and per-plantation
details (they can hold personal data).

    python portals.py discover          # on the box: -> data/portal_seeds.json (STF pages and files, Greens park ids)
    python portals.py                   # the pool task 'portal' (scrape.json); one queue item = one page / file / API call
"""
import gzip
import json
import os
import re
import sys
import time
from urllib.parse import urljoin

import crawl
import ddatls

STF = "https://stf.dda.org.in/"
GREENS_API = "https://ddagreens.dda.org.in/api/"
SEEDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "portal_seeds.json")
# STF menu postbacks that lead to public document pages (login, complaint forms and officer lists left out)
STF_SECTIONS = {
    "ctl00$LinkButton4": "Office memorandum and gazette notification",
    "ctl00$LinkButton5": "Status reports",
    "ctl00$LinkButton8": "Newspaper clips",
    "ctl00$lnk_PublicNotice": "Public notice",
    "ctl00$LNK_STFAGENDA": "STF meeting agenda",
    "ctl00$LinkButton9": "Minutes of STF meetings",
    "ctl00$quaterlyeeting": "Minutes of quarterly meetings in the Ministry",
}
FILE_RX = re.compile(r'href=["\']([^"\'#]+\.(?:pdf|jpe?g|png|docx?|xlsx?))["\']', re.I)
HIDDEN_RX = re.compile(r'<input[^>]+name="(__[A-Z]+)"[^>]+value="([^"]*)"')


def stf_page(html, url):
    """Pure: the section title, the text rows of its tables and the file links of one STF page."""
    files = sorted({urljoin(url, f.replace("&amp;", "&")) for f in FILE_RX.findall(html)} - {urljoin(url, "Doc/ManualMobileApp.PDF")})
    title = crawl._strip((re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S) or [None, ""])[1])
    rows = [r for t in crawl.extract_tables(html, url) for r in t["rows"] if any(c for c in r)]
    return {"url": url, "type": "stf-page", "title": title[:200], "rows": rows[:2000], "files": files,
            "n_files": len(files)}


# ---------------------------------------------------------------- discovery (box)

def discover():
    s = ddatls.make_session()
    home = s.get(STF, timeout=40).text
    form = dict(HIDDEN_RX.findall(home))
    pages, files = {}, set()
    for target, name in STF_SECTIONS.items():
        r = s.post(STF, data=dict(form, __EVENTTARGET=target, __EVENTARGUMENT=""), timeout=40)
        if r.url.rstrip("/") == STF.rstrip("/"):
            continue                       # the postback stays on the home page: nothing public behind it
        d = stf_page(r.text, r.url)
        pages[r.url] = {"section": name, "n_files": d["n_files"]}
        files.update(d["files"])
        time.sleep(1)
    parks = s.get(GREENS_API + "plantation/filter/parks", timeout=40).json()["data"]
    seeds = {"stf_pages": pages, "stf_files": sorted(files),
             "greens_parks": [{"id": p["id"], "code": p.get("park_code")} for p in parks],
             "discovered_at": time.strftime("%Y-%m-%d")}
    os.makedirs(os.path.dirname(SEEDS), exist_ok=True)
    with open(SEEDS, "w") as f:
        json.dump(seeds, f, indent=1)
    print(f"STF: {len(pages)} pages, {len(files)} files; Greens: {len(parks)} parks -> {SEEDS}")


def greens_endpoints(parks):
    """The API calls of one Greens scrape: dashboard, parks, and per park the summary and the species summaries."""
    out = ["plantation/dashboard", "plantation/filter/parks"]
    for p in parks:
        out += [f"Plantation/park-summary?parkId={p['id']}",
                f"plantation/species-summary?parkId={p['id']}&speciesType=Tree",
                f"plantation/species-summary?parkId={p['id']}&speciesType=Shrub"]
    return out


# ---------------------------------------------------------------- the pool task

def do_stf_page(hub, session, item):
    url = item["payload"]["url"]
    r, status = crawl.fetch(hub, session, url)
    body = crawl.read_body(hub, r) if r is not None else None
    if body is None:
        hub.complete([item["key"]], "failed", error=f"page did not load (HTTP {status})")
        return
    html = body.decode("utf-8", "replace")
    data = stf_page(html, url)
    data["section"] = item["payload"].get("section", "")
    data["fetched_at"] = int(time.time())
    try:
        hub.upload_many([(crawl.bucket_path(url, "pages") + ".html.gz", gzip.compress(body), "application/gzip")])
    except Exception as e:  # noqa: BLE001 - the record still counts
        data["upload_error"] = str(e)[:120]
    hub.record(crawl.record_id(url), data)
    hub.complete([item["key"]], "done", fetched=1)


def do_api(hub, session, item):
    url = GREENS_API + item["payload"]["endpoint"]
    r, status = crawl.fetch(hub, session, url)
    body = crawl.read_body(hub, r) if r is not None else None
    try:
        doc = json.loads(body) if body else None
    except ValueError:
        doc = None
    if doc is None:
        hub.complete([item["key"]], "failed", error=f"API did not answer with JSON (HTTP {status})")
        return
    data = {"url": url, "type": "greens-api", "endpoint": item["payload"]["endpoint"],
            "park_id": item["payload"].get("park_id"), "response": doc, "fetched_at": int(time.time())}
    hub.record(crawl.record_id(url), data)
    hub.complete([item["key"]], "done", fetched=1)


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
            kind = item["payload"].get("type")
            if kind == "stf-page":
                do_stf_page(hub, session, item)
            elif kind == "api":
                do_api(hub, session, item)
            else:
                crawl.do_doc(hub, session, item)
            time.sleep(max(0.5, hub.settings.get("delay_ms", 0) / 1000))
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


if __name__ == "__main__":
    if sys.argv[1:2] == ["discover"]:
        discover()
    else:
        main()
