"""Build an organised, query-ready copy of the DDA scrape in the member workspace database.

It reads the raw records the pool stored in scrape_hub (read-only) and writes clean tables to
schema `dda` in a workspace database (default: ws_<user>, which Metabase shows as "Workspace: <user>").
Re-running replaces the tables (one transaction), so it is safe to run while the scrape continues.

    python build_db.py                    # -> ws_$USER, schema dda
    python build_db.py --db ws_trideep

Tables (schema dda):
  pages           one row per HTML page (language, section, category, title, counts)
  documents       one row per linked document: stored / broken (404) / pending / failed, size, sha256
  listing_rows    one row per row of a Drupal listing table (serial, title, date, declared size, file)
  page_documents  page -> document links (where each document is linked from)
  external_links  page -> external URL
  tenders         listing rows that carry an NIT / tender reference, with office code and financial year
  work_awards     award letters (NIT reference where present)
  debarments      debarment / suspension orders and their withdrawals
  land_acq_awards land acquisition awards (award number, village)
  html_tables     every row of every plain HTML table (re-parsed from the raw pages, --html DIR)
  delineated_boundaries  PM-UDAY boundary maps of unauthorised colonies (/delineated-boundary)
  views: duplicate_files, size_mismatch, broken_links

Needs psycopg2 (pip install -r requirements-analysis.txt). Box only; not used by the pool task.
"""
import argparse
import json
import os
import re
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

import crawl

SRC_DB = "scrape_hub"
SIZE_RX = re.compile(r"Size\s*:?\s*([\d.,]+)\s*([KMG]?B)\b", re.I)
SERIAL_RX = re.compile(r"^\s*(\d{1,5})\s+")
NIT_RX = re.compile(
    r"(?:NIT|N\.I\.T\.?|Tender\s*(?:Notice|Invitation)?)\s*(?:No\.?|Number)?\s*[:.\-]*\s*"
    r"(\d[\d&, ]*\s*/.{0,60}?(?:\d{4}\s*-\s*\d{2,4}|(?<![\d.])\d{2}-\d{2}(?![-/.]?\d))(?:\s*/\s*[A-Za-z0-9().\-]+)*)", re.I)
NIT_ALT_RX = re.compile(r"\b(\d{1,4}/NIT/.{0,60}?\d{4}-\d{2,4})", re.I)
FY_RX = re.compile(r"(?<!\d)(\d{4}|\d{2})\s*-\s*(\d{4}|\d{2})(?!\d)")
FY_ALL_RX = re.compile(r"(?<!\d)(?=(\d{4}|\d{2})\s*-\s*(\d{4}|\d{2})(?!\d))")   # overlapping: 93-72-73
LAA_RX = re.compile(r"Award\s*No\.?\s*[-:]?\s*(\S+)\s+(.+)$", re.I)
UNIT = {"B": 1, "KB": 1024, "MB": 1024 ** 2, "GB": 1024 ** 3}


def src_rows(sql):
    conn = psycopg2.connect(dbname=SRC_DB, host="127.0.0.1",
                            options="-c statement_timeout=600000")
    with conn, conn.cursor(name="c") as cur:
        cur.itersize = 2000
        cur.execute(sql)
        for row in cur:
            yield row
    conn.close()


def lang_section(url):
    parts = [p for p in urlparse(url).path.split("/") if p]
    lang = "hi" if parts[:1] == ["hi"] else "en"
    if lang == "hi":
        parts = parts[1:]
    return lang, (parts[0] if parts else "(home)")


def doc_folder(url):
    """Folder under /sites/default/files/ and the upload month when the folder is YYYY-MM."""
    path = unquote(urlparse(url).path)
    m = re.search(r"/sites/default/files/([^/]+)/", path)
    folder = m.group(1) if m else "(root)"
    month = folder if re.fullmatch(r"\d{4}-\d{2}", folder) else None
    return folder, month


def fix_date(d, text):
    """Dates stored before the 2-digit-year fix: re-derive from the text, else pull 20yy back a century."""
    if d and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        y = int(d[:4])
        if 1900 <= y <= 2027:
            return d
        if 2027 < y <= 2099:
            return f"{y - 100}{d[4:]}"
        return None
    return crawl.iso_date(d or "") or crawl.iso_date(text)


def parse_row(text):
    serial = None
    m = SERIAL_RX.match(text)
    if m:
        serial = int(m.group(1))
        text = text[m.end():]
    size = None
    s = SIZE_RX.search(text)
    if s:
        try:
            size = int(float(s.group(1).replace(",", "")) * UNIT[s.group(2).upper()])
        except (ValueError, KeyError):
            size = None
        text = (text[:s.start()] + text[s.end():])
    title = re.sub(r"\s+", " ", text).strip(" .|-")
    return serial, title, size


def fin_year(text):
    """Indian financial year 'YYYY-YY' from '2026-27', '21-22' or '2005-2006'; None if the two halves
    are not consecutive years (a typing error on the site, e.g. '2026-26')."""
    for a, b in FY_ALL_RX.findall(text or ""):
        a4 = int(a) if len(a) == 4 else 2000 + int(a) if int(a) <= 40 else 1900 + int(a)
        if a4 < 1950 or a4 > 2030:
            continue
        if int(b[-2:]) == (a4 + 1) % 100:
            return f"{a4}-{(a4 + 1) % 100:02d}"
    return None


def nit_of(text):
    """(nit, office, fy) from a tender title: 'NIT No. 07/EE/HCD-10/DDA/2026-27' -> office 'EE/HCD-10'."""
    m = NIT_RX.search(text) or NIT_ALT_RX.search(text)
    if not m:
        return None, None, None
    nit = re.sub(r"\s+", "", m.group(1)).replace("//", "/").strip("/.")
    fy = fin_year(nit)
    parts = [p for p in nit.split("/")[1:]
             if p and p.upper() not in ("DDA", "NIT") and not FY_RX.fullmatch(p)
             and not re.match(r"(re-?\s?invit|corrigend|\(?re\b)", p, re.I)]
    office = "/".join(parts) or None
    return nit[:120], (office or None) and office[:60], fy


def laa_of(title):
    """Land acquisition award: (award_no, village, award_fy) from 'Award No-195-86-87 MAMOOR PUR'."""
    m = LAA_RX.search(title)
    if not m:
        return None
    no, village = m.group(1).strip("-:"), m.group(2).strip()
    return no, village[:120], fin_year(no)


DDL = """
DROP SCHEMA IF EXISTS dda_new CASCADE;
CREATE SCHEMA dda_new;
SET search_path = dda_new;
CREATE TABLE pages (
  url text PRIMARY KEY, record_id text, lang text, section text, category text, title text,
  description text, n_documents int, n_page_links int, n_rows int, n_external int,
  fetched_at timestamptz, content_sha256 text);
CREATE TABLE documents (
  url text PRIMARY KEY, record_id text, filename text, ext text, folder text, upload_month text,
  status text, http_status int, bytes bigint, sha256 text, content_type text, fetched_at timestamptz,
  n_linked_from int DEFAULT 0, first_linked_from text);
CREATE TABLE listing_rows (
  page_url text, row_no int, category text, lang text, serial int, title text, date date,
  declared_bytes bigint, doc_url text, n_docs int, PRIMARY KEY (page_url, row_no));
CREATE TABLE page_documents (page_url text, doc_url text, PRIMARY KEY (page_url, doc_url));
CREATE TABLE external_links (page_url text, url text, host text, PRIMARY KEY (page_url, url));
CREATE TABLE tenders (
  nit text, office text, fy text, title text, date date, doc_url text, source_category text,
  page_url text, row_no int, reinvited bool, PRIMARY KEY (page_url, row_no));
CREATE TABLE work_awards (
  title text, nit text, office text, fy text, date date, doc_url text, page_url text, row_no int,
  PRIMARY KEY (page_url, row_no));
CREATE TABLE debarments (
  title text, kind text, date date, doc_url text, page_url text, row_no int, PRIMARY KEY (page_url, row_no));
CREATE TABLE html_tables (
  page_url text, table_no int, row_no int, headers jsonb, cells jsonb, doc_urls text[],
  PRIMARY KEY (page_url, table_no, row_no));
CREATE TABLE delineated_boundaries (
  map_no int, reg_no text, colony text, remarks text, draft_uploaded date, final_uploaded date,
  map_url text, row_no int PRIMARY KEY);
CREATE TABLE land_acq_awards (
  award_no text, village text, award_fy text, title text, doc_url text, page_url text, row_no int,
  PRIMARY KEY (page_url, row_no));
"""

VIEWS = """
CREATE VIEW dda.duplicate_files AS
  SELECT sha256, count(*) AS copies, max(bytes) AS bytes, (count(*) - 1) * max(bytes) AS wasted_bytes,
         array_agg(url ORDER BY url) AS urls
  FROM dda.documents WHERE status = 'stored' AND bytes > 0 GROUP BY sha256 HAVING count(*) > 1;
CREATE VIEW dda.size_mismatch AS
  SELECT r.page_url, r.row_no, r.title, r.declared_bytes, d.bytes AS actual_bytes, d.url,
         round(d.bytes::numeric / nullif(r.declared_bytes, 0), 2) AS ratio
  FROM dda.listing_rows r JOIN dda.documents d ON d.url = r.doc_url
  WHERE d.status = 'stored' AND r.declared_bytes > 0
    AND (d.bytes < r.declared_bytes * 0.8 OR d.bytes > r.declared_bytes * 1.25)
    AND abs(d.bytes - r.declared_bytes) > 20480;
CREATE VIEW dda.broken_links AS
  SELECT d.url, d.http_status, d.folder, d.n_linked_from, d.first_linked_from
  FROM dda.documents d WHERE d.status = 'broken';
"""


def reg_no(text):
    from extract_colonies import reg_key
    return reg_key(text)


def raw_html(html_dir, *urls):
    """The raw page the pool stored (bucket dda-pages/pages/..., mirrored to html_dir)."""
    import gzip
    for u in urls:
        f = os.path.join(html_dir, crawl.bucket_path(u, "pages")[len("pages/"):] + ".html.gz")
        if os.path.exists(f):
            with gzip.open(f) as g:
                return g.read().decode("utf-8", "replace")
    return None


def boundaries(table):
    out = []
    for i, (cells, docs) in enumerate(zip(table["rows"], table["documents"])):
        cells = cells + [""] * (8 - len(cells))
        m = re.match(r"\s*(\d+)", cells[0])
        out.append((int(m.group(1)) if m else None, reg_no(cells[1]), cells[2].strip(" .")[:300],
                    cells[4] if cells[4] not in ("", "N/A") else None,
                    crawl.iso_date(cells[5]), crawl.iso_date(cells[7]),
                    crawl.canon_url(docs[-1]) if docs else None, i))
    return out


COLONY_VIEW = """
CREATE OR REPLACE VIEW dda.colony_boundary_status AS
  SELECT c.list, c.sl_no, c.reg_no, c.reg_key, c.name, c.pin,
         b.map_no, b.remarks, b.draft_uploaded, b.final_uploaded, b.map_url, d.status AS map_status,
         CASE WHEN b.reg_no IS NULL THEN 'not in boundary table'
              WHEN b.remarks ILIKE '%can not be delineated%' THEN 'can not be delineated'
              WHEN b.map_url IS NULL THEN 'no map file'
              WHEN b.final_uploaded IS NULL THEN 'map, no final date'
              ELSE 'final boundary published' END AS boundary_status
  FROM dda.unauthorised_colonies c
  LEFT JOIN (SELECT DISTINCT ON (reg_no) * FROM dda.delineated_boundaries
             ORDER BY reg_no, final_uploaded NULLS LAST) b ON b.reg_no = c.reg_key
  LEFT JOIN dda.documents d ON d.url = b.map_url;
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    ap.add_argument("--html", help="local mirror of the bucket's dda-pages/pages/ (mybucket get -r dda-pages/pages DIR)")
    args = ap.parse_args()
    html_rows, bounds = [], []

    pages, prows, links, ext_links, seen_pages = [], [], {}, [], set()
    tenders, awards, debar, laa = [], [], [], []
    for rid, at, data in src_rows("select record_id, scraped_at, data from projects.dda_pages"):
        if data.get("broken"):
            continue
        url = crawl.canon_url(data["url"])
        if url in seen_pages:          # a second spelling of one page (http/https): keep one
            continue
        seen_pages.add(url)
        lang, section = lang_section(url)
        pages.append((url, rid, lang, section, data.get("category"), data.get("title"),
                      data.get("description"), data.get("n_documents"), data.get("n_page_links"),
                      len(data.get("rows", [])), len(data.get("external_links", [])),
                      data.get("fetched_at"), data.get("content_sha256")))
        for d in data.get("documents", []) + [u for u in data.get("page_links", [])
                                              if crawl.classify(u) == "document"]:   # kmz etc. (older records)
            d = crawl.canon_url(d)
            if url not in links.setdefault(d, []):
                links[d].append(url)
        for e in data.get("external_links", []):
            ext_links.append((url, e, urlparse(e).netloc.lower()))
        tables = data.get("tables")
        if tables is None and args.html:
            h = raw_html(args.html, data["url"], url)
            tables = crawl.extract_tables(h, url) if h else []
        for t_no, t in enumerate(tables or []):
            for r_no, (cells, docs) in enumerate(zip(t["rows"], t["documents"])):
                html_rows.append((url, t_no, r_no, json.dumps(t["headers"], ensure_ascii=False),
                                  json.dumps(cells, ensure_ascii=False), [crawl.canon_url(d) for d in docs]))
            if url == "https://dda.gov.in/delineated-boundary" and t_no == 0:
                bounds = boundaries(t)
        cat = data.get("category") or ""
        for i, r in enumerate(data.get("rows", [])):
            text = r.get("text", "")
            serial, title, size = parse_row(text)
            date = fix_date(r.get("date"), text)
            docs = r.get("documents", [])
            doc = crawl.canon_url(docs[0]) if docs else None
            prows.append((url, i, cat, lang, serial, title[:1000], date, size, doc, len(docs)))
            key = (url, i)
            low = title.lower()
            nit, office, fy = nit_of(title)
            if "award" in low and ("letter" in low or "work award" in cat.lower()):
                awards.append((title[:1000], nit, office, fy, date, doc) + key)
            elif "debar" in low or "suspension" in low or "black" in low and "list" in low:
                kind = "withdrawal" if "withdraw" in low or "revok" in low else "order"
                debar.append((title[:1000], kind, date, doc) + key)
            elif nit or re.search(r"\btender\b", low) and "tender" in cat.lower():
                tenders.append((nit, office, fy, title[:1000], date, doc, cat) + key
                               + (bool(re.search(r"re-?\s?invit", low)),))
            a = laa_of(title) if "acquisition" in cat.lower() else None
            if a:
                laa.append(a + (title[:500], doc) + key)

    # documents: stored records + queue state for the rest
    docs = {}
    for rid, data in src_rows("select record_id, data from projects.dda_docs"):
        u = data.get("url")
        if not u or "&amp;" in u:
            continue
        u = crawl.canon_url(u)
        status = "broken" if data.get("broken") else "stored"
        if u in docs and docs[u][6] == "stored":
            continue
        folder, month = doc_folder(u)
        docs[u] = [u, rid, unquote(urlparse(u).path.rsplit("/", 1)[-1])[:300], data.get("ext"), folder, month,
                   status, data.get("status") or (200 if status == "stored" else None),
                   data.get("bytes"), data.get("sha256"), (data.get("content_type") or "").split(";")[0],
                   data.get("fetched_at")]
    for key, payload, qstatus, err in src_rows(
            "select key, payload, status, last_error from public.queue where project='dda-docs'"):
        u = payload.get("url")
        if not u or "&amp;" in u:     # a wrong spelling from before the '&amp;' fix; the right one is seeded
            continue
        u = crawl.canon_url(u)
        if u in docs:
            continue
        folder, month = doc_folder(u)
        m = re.search(r"HTTP (\d{3})", err or "")
        status = {"done": "stored", "failed": "failed", "claimed": "pending"}.get(qstatus, "pending")
        if status == "failed" and m and int(m.group(1)) in (404, 410):
            status = "broken"
        ext = (re.search(r"\.([a-z0-9]{1,6})$", urlparse(u).path.lower()) or [None, ""])[1]
        docs[u] = [u, crawl.record_id(u), unquote(urlparse(u).path.rsplit("/", 1)[-1])[:300], ext, folder, month,
                   status, int(m.group(1)) if m else None, None, None, None, None]
    # HEAD results for failed downloads (linkcheck.py): a 404/410 is a broken link on the site
    lc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkcheck.json")
    if os.path.exists(lc):
        for u, code in json.load(open(lc)).get("status", {}).items():
            row = docs.get(crawl.canon_url(u))
            if row and row[6] == "failed" and code in (404, 410):
                row[6], row[7] = "broken", code
    for u, row in docs.items():
        src = links.get(u, [])
        row += [len(src), src[0] if src else None]

    conn = psycopg2.connect(dbname=args.db, host="127.0.0.1")
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        ins = lambda table, rows: psycopg2.extras.execute_values(
            cur, f"INSERT INTO dda_new.{table} VALUES %s ON CONFLICT DO NOTHING", rows, page_size=1000)
        ins("pages", [p[:11] + (None if p[11] is None else psycopg2.TimestampFromTicks(p[11]), p[12])
                      for p in pages])
        ins("documents", [r[:11] + [None if r[11] is None else psycopg2.TimestampFromTicks(r[11])] + r[12:]
                          for r in docs.values()])
        ins("listing_rows", prows)
        ins("page_documents", [(p, d) for d, ps in links.items() for p in ps])
        ins("external_links", ext_links)
        ins("tenders", tenders)
        ins("work_awards", awards)
        ins("debarments", debar)
        ins("land_acq_awards", laa)
        ins("html_tables", html_rows)
        ins("delineated_boundaries", bounds)
        # keep the colony list (extract_colonies.py) across rebuilds
        cur.execute("SELECT to_regclass('dda.unauthorised_colonies') IS NOT NULL")
        if cur.fetchone()[0]:
            cur.execute("CREATE TABLE dda_new.unauthorised_colonies AS TABLE dda.unauthorised_colonies")
        cur.execute("DROP SCHEMA IF EXISTS dda CASCADE; ALTER SCHEMA dda_new RENAME TO dda;")
        cur.execute(VIEWS)
        cur.execute("SELECT to_regclass('dda.unauthorised_colonies') IS NOT NULL")
        if cur.fetchone()[0]:
            cur.execute(COLONY_VIEW)
        cur.execute("COMMENT ON SCHEMA dda IS %s",
                    ("DDA (dda.gov.in) scrape, built by s1d-labs/dda build_db.py from scrape_hub projects dda-pages/dda-docs",))
    conn.close()
    st = {k: len(v) for k, v in [("pages", pages), ("documents", docs), ("listing_rows", prows),
                                 ("tenders", tenders), ("work_awards", awards), ("debarments", debar),
                                 ("land_acq_awards", laa), ("external_links", ext_links),
                                 ("html_tables", html_rows), ("delineated_boundaries", bounds)]}
    print(json.dumps(st))


if __name__ == "__main__":
    main()
