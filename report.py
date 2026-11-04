"""Build a coverage report for the DDA scrape.

It reads two sources and writes report.json plus a short summary:
  - seeds.json       : the discovery scope (pages and documents found on the site)
  - scrape_hub (DB)  : what the pool has stored (records, queue, failures, probe, runs)

The database part uses the `psql` client and is read-only. Run it on the box:

    python report.py                 # full report -> report.json
    python report.py --no-db         # discovery scope only (no hub database)

It names no private individuals. It reports counts, categories and coverage only.
"""
import argparse
import json
import re
import subprocess
import time
from collections import Counter
from urllib.parse import urlparse

PAGES_PROJECT = "dda-pages"
DOCS_PROJECT = "dda-docs"
PROBE = "dda:dda.gov.in"


def psql(sql, db="scrape_hub"):
    """Run one query, return rows as lists of strings (tab-separated, no header)."""
    out = subprocess.run(["psql", db, "-tAF", "\t", "-c", sql],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return [line.split("\t") for line in out.stdout.splitlines() if line]


def one(sql, db="scrape_hub"):
    rows = psql(sql, db)
    return rows[0][0] if rows and rows[0] else None


def discovery_scope(seeds_path):
    try:
        s = json.load(open(seeds_path))
    except FileNotFoundError:
        return None
    pages = s.get("pages", [])
    docs = s.get("documents", [])
    doc_ext = Counter()
    for u in docs:
        m = re.search(r"\.([a-z0-9]{1,6})$", urlparse(u).path.lower())
        doc_ext[m.group(1) if m else "?"] += 1
    cat = Counter()
    for u in pages:
        seg = urlparse(u).path.strip("/").split("/")[0] or "(home)"
        cat[seg] += 1
    return {
        "pages_discovered": len(pages),
        "documents_discovered": len(docs),
        "documents_by_type": dict(doc_ext.most_common()),
        "top_sections": dict(cat.most_common(25)),
        "external_hosts": s.get("external", {}),
        "discovery_errors": len(s.get("errors", {})),
        "discovery_queued_unreached": s.get("stats", {}).get("pages_queued_unreached", 0),
        "discovery_stats": s.get("stats", {}),
    }


def db_section():
    probe_rows = psql(f"select ok, at, ms, coalesce(detail,'') from public.probes "
                      f"where target='{PROBE}' order by at desc limit 1;")
    probe = None
    if probe_rows:
        ok, at, ms, detail = probe_rows[0]
        probe = {"ok": ok == "t", "at": at, "ms": int(ms) if ms.isdigit() else ms, "detail": detail[:160]}

    def proj_stats(proj):
        q = psql(f"select status, count(*) from public.queue where project='{proj}' group by status;")
        queue = {r[0]: int(r[1]) for r in q}
        recs = int(one(f"select count(*) from public.records where project='{proj}';") or 0)
        fetched = int(one(f"select coalesce(sum(fetched),0) from public.queue where project='{proj}' and status='done';") or 0)
        return {"queue": queue, "records": recs, "fetched_sum": fetched}

    pages = proj_stats(PAGES_PROJECT)
    docs = proj_stats(DOCS_PROJECT)

    # document types + total bytes from stored records
    doc_types = {r[0]: int(r[1]) for r in psql(
        f"select coalesce(data->>'ext','?'), count(*) from public.records "
        f"where project='{DOCS_PROJECT}' group by 1 order by 2 desc;")}
    total_bytes = int(one(f"select coalesce(sum((data->>'bytes')::bigint),0) from public.records "
                          f"where project='{DOCS_PROJECT}' and data ? 'bytes';") or 0)
    # page categories from stored records
    page_cats = {r[0]: int(r[1]) for r in psql(
        f"select coalesce(data->>'category','?'), count(*) from public.records "
        f"where project='{PAGES_PROJECT}' group by 1 order by 2 desc limit 30;")}

    failures = [{"project": r[0], "kind": r[1], "reason": r[2][:120], "attempts": r[3]}
                for r in psql("select project, kind, reason, attempts from public.failures "
                              "where project like 'dda%' order by last_seen desc limit 50;")]
    runs = [{"project": r[0], "state": r[1], "records": r[2], "errors": r[3], "egress_ip": r[4]}
            for r in psql("select project, state, records, errors, coalesce(egress_ip::text,'') "
                          "from public.runs where project like 'dda%' order by started_at desc limit 20;")]

    return {
        "probe": probe,
        "pages": pages,
        "docs": docs,
        "documents_by_type_stored": doc_types,
        "documents_total_bytes": total_bytes,
        "page_categories_stored": page_cats,
        "failures": failures,
        "failures_count": len(failures),
        "runs": runs,
    }


def coverage(disc, db):
    if not disc or not db:
        return {}
    pd = disc["pages_discovered"] or 1
    dd = disc["documents_discovered"] or 1
    ps = db["pages"]["records"]
    ds = db["docs"]["records"]
    return {
        "pages_scraped": ps, "pages_discovered": disc["pages_discovered"],
        "pages_coverage_pct": round(100 * ps / pd, 1),
        "pages_not_scraped": max(0, disc["pages_discovered"] - ps),
        "documents_scraped": ds, "documents_discovered": disc["documents_discovered"],
        "documents_coverage_pct": round(100 * ds / dd, 1),
        "documents_not_scraped": max(0, disc["documents_discovered"] - ds),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="seeds.json")
    ap.add_argument("--out", default="report.json")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    report = {"generated_at": int(time.time()), "site": "https://dda.gov.in/"}
    report["discovery"] = discovery_scope(args.seeds)
    if not args.no_db:
        try:
            report["hub"] = db_section()
            report["coverage"] = coverage(report["discovery"], report["hub"])
        except Exception as e:
            report["hub_error"] = str(e)[:300]

    with open(args.out, "w") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)

    d = report.get("discovery") or {}
    print("=== DDA scrape report ===")
    print("pages discovered   :", d.get("pages_discovered"))
    print("documents discovered:", d.get("documents_discovered"))
    print("documents by type  :", d.get("documents_by_type"))
    if "hub" in report:
        h = report["hub"]
        print("probe              :", h.get("probe"))
        print("pages scraped      :", h["pages"]["records"], "| queue", h["pages"]["queue"])
        print("docs scraped       :", h["docs"]["records"], "| queue", h["docs"]["queue"],
              "| bytes", h["documents_total_bytes"])
        print("failures           :", h["failures_count"])
        print("coverage           :", report.get("coverage"))
    if "hub_error" in report:
        print("hub_error          :", report["hub_error"])
    print("wrote", args.out)


if __name__ == "__main__":
    main()
