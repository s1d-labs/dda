"""Figures for the DDA analysis report, from the organised tables (build_db.py, extract_colonies.py).

    python analyze.py                 # ws_$USER -> analysis.json
    python analyze.py --db ws_trideep --out analysis.json

Counts and categories only. It does not output names of contractors or other persons.
"""
import argparse
import json
import os
import subprocess

Q = {
    # documents
    "doc_status": "select status, count(*) from dda.documents group by 1 order by 2 desc",
    "doc_types": """select coalesce(nullif(ext,''),'(none)'), count(*), coalesce(sum(bytes),0)
                    from dda.documents group by 1 order by 2 desc""",
    "doc_bytes_stored": "select count(*), sum(bytes), percentile_cont(0.5) within group (order by bytes) "
                        "from dda.documents where status='stored'",
    "doc_size_bands": """select case when bytes < 100e3 then '< 100 KB' when bytes < 1e6 then '100 KB - 1 MB'
                         when bytes < 10e6 then '1 - 10 MB' when bytes < 100e6 then '10 - 100 MB' else '>= 100 MB' end,
                         count(*), min(bytes) from dda.documents where status='stored' group by 1 order by 3""",
    "doc_largest": """select folder, ext, bytes from dda.documents where status='stored'
                      order by bytes desc limit 10""",
    "doc_folders": """select folder, count(*), count(*) filter (where status='broken')
                      from dda.documents group by 1 order by 2 desc limit 15""",
    "doc_empty": "select count(*) from dda.documents where status='stored' and bytes = 0",
    "duplicates": "select count(*), coalesce(sum(copies-1),0), coalesce(sum(wasted_bytes),0), coalesce(max(copies),0) "
                  "from dda.duplicate_files",
    "size_mismatch": "select count(*) from dda.size_mismatch",
    "broken_by_folder": "select folder, count(*) from dda.broken_links group by 1 order by 2 desc limit 10",
    "upload_months": """select upload_month, count(*) from dda.documents where upload_month is not null
                        group by 1 order by 1""",
    # pages
    "pages_lang": "select lang, count(*) from dda.pages group by 1",
    "pages_sections": "select section, count(*) from dda.pages where lang='en' group by 1 order by 2 desc limit 15",
    "pages_no_title": "select count(*) from dda.pages where coalesce(title,'') = ''",
    "external_hosts": """select host, count(distinct url), count(distinct page_url) from dda.external_links
                         group by 1 order by 3 desc limit 15""",
    "external_http": "select count(distinct url) from dda.external_links where url like 'http://%'",
    "listing_rows": "select count(*), count(date), count(doc_url), count(declared_bytes) from dda.listing_rows",
    "rows_per_year": """select extract(year from date)::int, count(*) from dda.listing_rows
                        where date is not null group by 1 order by 1""",
    "latest_by_category": """select category, max(date), count(*) from dda.listing_rows where date is not null
                             and lang='en' group by 1 having count(*) >= 20 order by 2 asc limit 12""",
    # tenders and awards
    "tenders_fy": """select fy, count(*), count(*) filter (where reinvited) from dda.tenders
                     where fy is not null group by 1 order by 1""",
    "tenders_total": "select count(*), count(distinct nit), count(fy), count(*) filter (where reinvited) from dda.tenders",
    "tender_offices": "select office, count(*) from dda.tenders where office is not null group by 1 order by 2 desc limit 12",
    "work_awards": "select count(*), count(nit), count(date) from dda.work_awards",
    "award_concentration": """with a as (select lower(regexp_replace(title, '^.*?\\m(to|of)\\M\\s*', '', 'i')) who, count(*) n
                              from dda.work_awards group by 1)
                              select count(*), sum(n), (select sum(n) from (select n from a order by n desc limit 10) t)
                              from a""",
    "debarments": "select kind, count(*) from dda.debarments group by 1",
    "debarments_year": """select extract(year from date)::int, count(*) from dda.debarments
                          where kind='order' and date is not null group by 1 order by 1""",
    "land_acq_decade": """select coalesce(left(award_fy,3)||'0s','(no year)'), count(*) from dda.land_acq_awards
                          group by 1 order by 1""",
    "land_acq_villages": "select village, count(*) from dda.land_acq_awards group by 1 order by 2 desc limit 10",
    "authority_meetings": """select (extract(year from date)::int/10*10), count(*) from dda.listing_rows
                             where category='Authority Meeting' and date is not null group by 1 order by 1""",
    # colonies
    "colonies": "select list, count(*), count(pin) from dda.unauthorised_colonies group by 1",
    "colony_status": """select boundary_status, count(*) from dda.colony_boundary_status where list='1731'
                        group by 1 order by 2 desc""",
    "colony_dup_reg": """select count(*) from (select reg_key from dda.unauthorised_colonies where list='1731'
                         group by 1 having count(*) > 1) t""",
    "boundary_rows": """select count(*), count(map_url), count(final_uploaded), min(final_uploaded), max(final_uploaded),
                        count(*) filter (where remarks ilike '%can not be delineated%'),
                        count(*) filter (where remarks ilike '%shapefile%') from dda.delineated_boundaries""",
    "boundary_not_in_list": """select count(*) from dda.delineated_boundaries b
                               left join dda.unauthorised_colonies c on c.reg_key=b.reg_no where c.reg_key is null""",
    "colony_pins": """select pin, count(*) from dda.unauthorised_colonies where list='1731' and pin is not null
                      group by 1 order by 2 desc limit 12""",
    # DDA on the central e-procurement portal (link_eprocure.py); counts and values only, no bidder names
    "ep_years": """select extract(year from published_at)::int, count(*), round(sum(tender_value)/1e7),
                   count(*) filter (where bids_count = 1), count(*) filter (where bids_count >= 1)
                   from dda.eprocure_tenders where is_real and published_at >= '2014-01-01' group by 1 order by 1""",
    "ep_stage": "select stage_group, count(*) from dda.eprocure_tenders group by 1 order by 2 desc",
    "ep_award_ratio": """select count(*), percentile_cont(0.5) within group (order by awarded_value / tender_value),
                         count(*) filter (where awarded_value < tender_value)
                         from dda.eprocure_tenders where awarded_value > 0 and tender_value > 0""",
    "ep_links": """select (select count(*) from dda.tenders where nit is not null),
                          (select count(distinct (page_url, row_no)) from dda.tender_links),
                          (select count(*) from dda.work_awards where nit is not null),
                          (select count(distinct (page_url, row_no)) from dda.award_links)""",
    "ep_award_letter_stage": """select e.stage_group, count(distinct e.tender_id) from dda.award_links l
                                join dda.eprocure_tenders e using (tender_id) group by 1 order by 2 desc""",
    "ep_rounds": """select n_rounds, count(*) from (select nit_key, count(*) n_rounds from dda.eprocure_tenders
                    where nit_key is not null group by 1) t group by 1 order by 1 limit 8""",
    # privacy indicator: contractor enlistment files (counts only)
    "enlistment_files": """select count(*), count(*) filter (where filename ~* 'solv'),
                           count(*) filter (where filename ~* 'appli'),
                           count(*) filter (where filename ~* 'perform'),
                           count(*) filter (where filename ~* 'enlist') from dda.documents where folder ~* '^class-'""",
}


def run(db, sql):
    env = dict(os.environ, PGOPTIONS="-c statement_timeout=300000")
    out = subprocess.run(["psql", db, "-tAF", "\t", "-c", sql], capture_output=True, text=True, env=env, check=True)
    rows = []
    for line in out.stdout.splitlines():
        if not line:
            continue
        cells = []
        for c in line.split("\t"):
            try:
                cells.append(int(c))
            except ValueError:
                try:
                    cells.append(float(c))
                except ValueError:
                    cells.append(c if c != "" else None)
        rows.append(cells)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    ap.add_argument("--out", default="analysis.json")
    args = ap.parse_args()
    res = {k: run(args.db, sql) for k, sql in Q.items()}
    # the full discovered scope (seeds.json, one spelling per URL) and the hub queue state
    import family
    res["scope"] = {"pages": len(family.PAGE_ITEMS), "documents": len(family.DOC_ITEMS)}
    res["ep_peer_awarded"] = run("scrape_hub", """select org_code, count(*),
        round(100.0 * count(*) filter (where stage_group = 'awarded') / count(*), 1)
        from eprocure.tender_facts where org_code in (select org_code from eprocure.org_index
        order by tenders desc limit 10) group by 1 order by 2 desc""")
    try:
        res["doc_text"] = run(args.db, """select count(*), count(*) filter (where has_text), coalesce(sum(chars), 0),
            (select count(*) from dda.documents where status='stored' and ext='pdf') from dda.document_text""")
        res["doc_text_search"] = run(args.db, """select q, (select count(*) from dda.document_text
            where to_tsvector('simple', coalesce(text,'')) @@ plainto_tsquery('simple', q)) from
            unnest(array['land pooling','unauthorised colony','encroachment','demolition','arbitration','debarment']) q""")
    except subprocess.CalledProcessError:
        pass
    if os.path.exists("pdf_census.json"):
        res["pdf_census"] = json.load(open("pdf_census.json")).get("summary")
    res["hub_queue"] = run("scrape_hub", "select project, status, count(*) from public.queue "
                                         "where project in ('dda-pages','dda-docs') group by 1,2 order by 1,2")
    import time
    res["_generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(args.out, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=str)
    print(f"wrote {args.out}: {len(Q)} figures")


if __name__ == "__main__":
    main()
