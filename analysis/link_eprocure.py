"""Link the tender notices on dda.gov.in to DDA's tenders on the central e-procurement portal.

The team database (scrape_hub, schema eprocure) already holds DDA's eprocure.gov.in tenders (org_code 'DDA'):
value, EMD, bid counts, award. The DDA site holds the notice PDFs. Both use the same NIT reference
('07/EE/ELD-8/DDA/2026-27'), so a key of (number, office, financial year) links them.

    python -m analysis.link_eprocure                # -> ws_$USER: dda.eprocure_tenders, dda.tender_links

Tables:
  eprocure_tenders  DDA tenders on eprocure (no bidder names): tender_id, ref_no, nit_key, title, stage, values, bids, dates
  tender_links      dda.tenders row (page_url, row_no) -> eprocure tender_id, by nit_key
  award_links       dda.work_awards row (award letter on the DDA site) -> eprocure tender_id, by nit_key.
                    eprocure shows only 2% of DDA tenders as awarded; the site's award letters fill part of that gap.
"""
import argparse
import os
import re

from analysis.build_db import fin_year


ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
# parts that are not the office: the authority, the notice type, a zone, a title of the officer
NOT_OFFICE = {"DDA", "NIT", "NIQ", "EZ", "WZ", "NZ", "SZ", "SEZ", "NWZ", "DD", "DYDIRECTOR", "DIRECTOR", "DIRH",
              "EE", "EEE", "AE", "AEP", "SE"}   # officer titles: written or left out at random


def office_part(part):
    """One part of the office code in one spelling: 'Hort. 3' / 'HD-III' -> 'HD3', 'EZ' -> ''."""
    p = re.sub(r"[^A-Za-z0-9]", "", part).upper()
    if p in NOT_OFFICE:
        return ""
    p = re.sub(r"^(?:DD)?HORT(?:ICULTURE)?(?:DIVN?|DIVISION)?(?:NO)?", "HD", p)
    p = re.sub(r"^(?:AEP|EE)*SPORTS?DIV(?:ISION|N)?(?:NO)?", "SPD", p)     # 'Sports Divn.-1', 'Sports Division-1'
    p = re.sub(r"^EEE(?=[A-Z])", "", p)                                     # 'EE(E)ELD10' written as one part
    m = re.fullmatch(r"([A-Z]*?[A-Z])(I{1,3}|IV|VI{0,3}|IX|XI{0,2})", p)
    if m and m.group(1) in ("HD", "ELD", "EMD", "HCD", "RMD", "NMD", "ND", "SD", "WD", "ED", "PD", "CD", "SPD", "SMD"):
        p = m.group(1) + str(ROMAN[m.group(2)])
    return p


def nit_keys(ref):
    """All keys of one reference. '07/EE/ELD-8/DDA/NIT/2026-27_R6' -> ['7|EEELD8|2026-27']; a combined notice
    '13,14&15/EE/EMD-7/DDA/2024-25' -> one key per number. The office is every part except DDA/NIT and the
    year; re-invite and recall marks are dropped. An NIQ (quotation) has its own number series: 'Q' prefix."""
    if not ref:
        return []
    t = re.sub(r"(?i)_r\d+$|\(?re-?\s?invit\w*\)?|/re-?invit\w*|\(?re-?\s?call\w*\)?", "", ref)
    t = re.sub(r"(?i)DDA(?=\s*\d{4}\s*-)", "DDA/", t)          # '14/RSC/DDA2025-26' -> '14/RSC/DDA/2025-26'
    kind = "Q" if re.match(r"(?i)^\s*(short\s+)?(niq|n\.i\.q)", t) else ""
    # 'NIT No. 05/...', 'Short NIQ No. 01/...', 'E-Tender Notice No: 06/...' -> '05/...'
    t = re.sub(r"(?i)^\s*(short\s+)?(e-?\s?tender\s+notice|nit|niq|n\.i\.[tq]\.?|tender)\s*(no\.?|number)?\s*[:.\-]*\s*", "", t)
    parts = [p.strip() for p in re.split(r"/+", t) if p.strip()]
    if len(parts) < 2:
        return []
    nums = re.findall(r"\d+", parts[0]) if re.fullmatch(r"[\d\s,&and]+", parts[0]) else []
    if not nums:
        return []
    fy = fin_year(t)
    office = "".join(office_part(p) for p in parts[1:] if not re.fullmatch(r"\d{2,4}\s*-\s*\d{2,4}.*", p))
    if not fy or not office:
        return []
    return [f"{kind}{int(x)}|{office}|{fy}" for x in dict.fromkeys(nums)]


def nit_key(ref):
    """The key of the first (or only) number of a reference; None when it has no number, office or year."""
    keys = nit_keys(ref)
    return keys[0] if keys else None


def main():
    import psycopg2
    import psycopg2.extras
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
        site = [(p, r, k) for p, r, n in cur.fetchall() for k in (nit_keys(n) or [None])]
        cur.execute("""DROP TABLE IF EXISTS dda.tender_links;
            CREATE TABLE dda.tender_links (page_url text, row_no int, nit_key text, tender_id text,
              match text DEFAULT 'key', PRIMARY KEY (page_url, row_no, tender_id));""")
        cur.execute("CREATE TEMP TABLE s (page_url text, row_no int, nit_key text)")
        psycopg2.extras.execute_values(cur, "INSERT INTO s VALUES %s", [x for x in site if x[2]])
        cur.execute("""INSERT INTO dda.tender_links
            SELECT s.page_url, s.row_no, s.nit_key, e.tender_id, 'key' FROM s JOIN dda.eprocure_tenders e USING (nit_key)
            ON CONFLICT DO NOTHING""")
        cur.execute("select page_url, row_no, nit from dda.work_awards where nit is not null")
        aw = [(p, r, k) for p, r, n in cur.fetchall() for k in (nit_keys(n) or [None])]
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
        # why a site tender row has no link: no key / probably the same tender with the office written another way
        # (same number and year, and one office token such as 'ELD13' in common) / not found on eprocure
        cur.execute("select nit_key, ref_no, tender_id from dda.eprocure_tenders where nit_key is not null")
        by_num_fy = {}
        for k, ref, tid in cur.fetchall():
            num, off, fy = k.split("|")
            by_num_fy.setdefault((num, fy), []).append((off, ref, k, tid))
        cur.execute("""select t.page_url, t.row_no, t.nit, t.office, t.fy, t.date from dda.tenders t
                       where t.nit is not null and not exists (select 1 from dda.tender_links l
                             where l.page_url = t.page_url and l.row_no = t.row_no)""")
        unl, extra = [], []
        for page_url, row_no, nit, office, fy, date in cur.fetchall():
            keys = nit_keys(nit)
            cands = []
            for k in keys:
                num, off, kfy = k.split("|")
                toks = set(re.findall(r"[A-Z]+\d+", off)) or {off}
                cands += [c for c in by_num_fy.get((num, kfy), []) if any(t in c[0] for t in toks)]
            if cands and len({c[2] for c in cands}) == 1:
                # one eprocure reference (with its re-tender rounds) shares the number, the year and an office
                # token: 'NMD-2(ND-3)' on the site is 'EE/NMD-2' on eprocure. Link it, marked as such.
                extra += [(page_url, row_no, cands[0][2], c[3], "office token") for c in cands]
                continue
            reason = ("no key (no office or year in the NIT)" if not keys else
                      "several possible matches" if cands else "not found on eprocure")
            unl.append((page_url, row_no, nit, office, fy, date, keys[0] if keys else None,
                        " ; ".join(sorted({c[1] for c in cands})[:5]) or None, reason))
        if extra:
            psycopg2.extras.execute_values(cur, "INSERT INTO dda.tender_links VALUES %s ON CONFLICT DO NOTHING", extra)
        cur.execute("select count(*), count(distinct (page_url, row_no)) from dda.tender_links")
        links, linked_rows = cur.fetchone()
        cur.execute("""DROP TABLE IF EXISTS dda.tender_unlinked;
            CREATE TABLE dda.tender_unlinked (page_url text, row_no int, nit text, office text, fy text, date date,
              nit_key text, candidates text, reason text, PRIMARY KEY (page_url, row_no))""")
        if unl:
            psycopg2.extras.execute_values(cur, "INSERT INTO dda.tender_unlinked VALUES %s", unl)
    dst.close()
    keyed = len({(x[0], x[1]) for x in site if x[2]})
    n_site = len({(x[0], x[1]) for x in site})
    print(f"eprocure DDA tenders: {len(ep)} ({sum(1 for e in ep if e[2])} with a key); "
          f"site tender rows with NIT: {n_site} ({keyed} keyed); linked rows: {linked_rows} ({links} links); "
          f"award letters with NIT: {len({(x[0], x[1]) for x in aw})}, linked: {award_rows}")


if __name__ == "__main__":
    main()
