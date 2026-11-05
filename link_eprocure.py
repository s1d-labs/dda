"""Link the tender notices on dda.gov.in to DDA's tenders on the central e-procurement portal.

The team database (scrape_hub, schema eprocure) already holds DDA's eprocure.gov.in tenders (org_code 'DDA'):
value, EMD, bid counts, award. The DDA site holds the notice PDFs. Both use the same NIT reference
('07/EE/ELD-8/DDA/2026-27'), so a key of (number, office, financial year) links them.

    python link_eprocure.py                # -> ws_$USER: dda.eprocure_tenders, dda.tender_links

Tables:
  eprocure_tenders  DDA tenders on eprocure (no bidder names): tender_id, ref_no, nit_key, title, stage, values, bids, dates
  tender_links      dda.tenders row (page_url, row_no) -> eprocure tender_id, by nit_key
  award_links       dda.work_awards row (award letter on the DDA site) -> eprocure tender_id, by nit_key.
                    eprocure shows only 2% of DDA tenders as awarded; the site's award letters fill part of that gap.
"""
import argparse
import os
import re

import psycopg2
import psycopg2.extras

from build_db import fin_year


def nit_key(ref):
    """'07/EE/ELD-8/DDA/NIT/2026-27_R6' and 'NIT No. 7/EE/ELD-8/DDA/2026-27 (Re-invite)' -> '7|EEELD8|2026-27'.
    Number(s) first; the office is every other part except DDA/NIT/re-invite marks; then the financial year."""
    if not ref:
        return None
    t = re.sub(r"(?i)_r\d+$|\(?re-?\s?invit\w*\)?|/re-?invit\w*", "", ref)
    # 'NIT No. 05/...', 'Short NIQ No. 01/...', 'E-Tender Notice No: 06/...' -> '05/...'.
    # An NIQ (quotation) has its own number series, so its key starts with 'Q'.
    kind = "Q" if re.match(r"(?i)^\s*(short\s+)?(niq|n\.i\.q)", t) else ""
    t = re.sub(r"(?i)^\s*(short\s+)?(e-?\s?tender\s+notice|nit|niq|n\.i\.[tq]\.?|tender)\s*(no\.?|number)?\s*[:.\-]*\s*", "", t)
    parts = [p.strip() for p in re.split(r"/+", t) if p.strip()]
    if len(parts) < 2:
        return None
    m = re.match(r"0*(\d+)", parts[0])
    if not m:
        return None
    fy = fin_year(t)
    office = "".join(re.sub(r"[^A-Za-z0-9]", "", p).upper() for p in parts[1:]
                     if p.upper() not in ("DDA", "NIT") and not re.fullmatch(r"\d{2,4}\s*-\s*\d{2,4}.*", p))
    if not fy or not office:
        return None
    return f"{kind}{m.group(1)}|{office}|{fy}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    args = ap.parse_args()
    src = psycopg2.connect(dbname="scrape_hub", host="127.0.0.1", options="-c statement_timeout=600000")
    with src, src.cursor() as cur:
        cur.execute("""select f.tender_id, i.ref_no, left(i.title, 300), f.stage_group, f.stage, f.tender_type,
                              f.tender_category, f.tender_value, f.emd_amount, f.bids_count, f.qualified_bids_count,
                              f.awarded_value, f.published_at, f.bid_submission_end_at, f.awarded_at, f.is_real
                       from eprocure.tender_facts f join eprocure.tender_index i using (tender_id)
                       where f.org_code = 'DDA'""")
        rows = cur.fetchall()
    src.close()
    ep = [(r[0], r[1], nit_key(r[1])) + tuple(r[2:]) for r in rows]

    dst = psycopg2.connect(dbname=args.db, host="127.0.0.1")
    with dst, dst.cursor() as cur:
        cur.execute("""DROP TABLE IF EXISTS dda.eprocure_tenders CASCADE;
            CREATE TABLE dda.eprocure_tenders (tender_id text PRIMARY KEY, ref_no text, nit_key text, title text,
              stage_group text, stage text, tender_type text, tender_category text, tender_value numeric,
              emd_amount numeric, bids_count int, qualified_bids_count int, awarded_value numeric,
              published_at timestamp, bid_submission_end_at timestamp, awarded_at timestamp, is_real bool);
            CREATE INDEX ON dda.eprocure_tenders (nit_key);""")
        psycopg2.extras.execute_values(cur, "INSERT INTO dda.eprocure_tenders VALUES %s ON CONFLICT DO NOTHING",
                                       ep, page_size=2000)
        cur.execute("select page_url, row_no, nit from dda.tenders where nit is not null")
        site = [(p, r, nit_key(n)) for p, r, n in cur.fetchall()]
        cur.execute("""DROP TABLE IF EXISTS dda.tender_links;
            CREATE TABLE dda.tender_links (page_url text, row_no int, nit_key text, tender_id text,
              PRIMARY KEY (page_url, row_no, tender_id));""")
        cur.execute("CREATE TEMP TABLE s (page_url text, row_no int, nit_key text)")
        psycopg2.extras.execute_values(cur, "INSERT INTO s VALUES %s", [x for x in site if x[2]])
        cur.execute("""INSERT INTO dda.tender_links
            SELECT s.page_url, s.row_no, s.nit_key, e.tender_id FROM s JOIN dda.eprocure_tenders e USING (nit_key)
            ON CONFLICT DO NOTHING""")
        cur.execute("select count(*), count(distinct (page_url, row_no)) from dda.tender_links")
        links, linked_rows = cur.fetchone()
        cur.execute("select page_url, row_no, nit from dda.work_awards where nit is not null")
        aw = [(p, r, nit_key(n)) for p, r, n in cur.fetchall()]
        cur.execute("""DROP TABLE IF EXISTS dda.award_links;
            CREATE TABLE dda.award_links (page_url text, row_no int, nit_key text, tender_id text,
              PRIMARY KEY (page_url, row_no, tender_id));
            CREATE TEMP TABLE a (page_url text, row_no int, nit_key text)""")
        psycopg2.extras.execute_values(cur, "INSERT INTO a VALUES %s", [x for x in aw if x[2]] or [(None, None, None)])
        cur.execute("""INSERT INTO dda.award_links
            SELECT a.page_url, a.row_no, a.nit_key, e.tender_id FROM a JOIN dda.eprocure_tenders e USING (nit_key)
            ON CONFLICT DO NOTHING""")
        cur.execute("select count(distinct (page_url, row_no)) from dda.award_links")
        award_rows = cur.fetchone()[0]
    dst.close()
    keyed = sum(1 for x in site if x[2])
    print(f"eprocure DDA tenders: {len(ep)} ({sum(1 for e in ep if e[2])} with a key); "
          f"site tender rows with NIT: {len(site)} ({keyed} keyed); linked rows: {linked_rows} ({links} links); "
          f"award letters with NIT: {len(aw)}, linked: {award_rows}")


if __name__ == "__main__":
    main()
