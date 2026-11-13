"""Write data/watch_known.json from what the weekly watch stored (box only; reads the hub database).

watch.py compares the links on the listings with the known scope. seeds.json changes only after a discovery
run, so without this file a new file would be downloaded again every week. This step adds every page and file that
dda-watch stored, and every new page link that did not load (404 or not HTML), to the known list.

    python -m analysis.fold_watch          # then commit data/watch_known.json (the pool reads it from main)
"""
import json
import os
import subprocess

import crawl

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "watch_known.json")


def rows(sql):
    env = dict(os.environ, PGOPTIONS="-c statement_timeout=120000")
    out = subprocess.run(["psql", "scrape_hub", "-tAc", sql], capture_output=True, text=True, env=env, check=True)
    return [json.loads(line) for line in out.stdout.splitlines() if line]


def main():
    known = json.load(open(OUT)) if os.path.exists(OUT) else {}
    docs, pages, dead = set(known.get("documents", [])), set(known.get("pages", [])), set(known.get("dead_pages", []))
    for d in rows("select data::text from public.records where project = 'dda-watch'"):
        t, url = d.get("type"), d.get("url")
        if t in ("document", "doc") and url:
            docs.add(crawl.canon_url(url))
        elif t == "page" and url:
            pages.add(crawl.canon_url(url))
        elif t == "watch":
            if "dead_page_urls" in d:
                dead.update(crawl.canon_url(u) for u in d["dead_page_urls"])
            elif d.get("stored_pages", 0) == 0:
                # older summaries: no page of the week was stored, so every new page link was dead
                dead.update(crawl.canon_url(u) for u in d.get("new_page_urls", []))
    dead -= pages
    out = {"about": "pages and files the weekly watch already stored or found dead; written by analysis.fold_watch",
           "documents": sorted(docs), "pages": sorted(pages), "dead_pages": sorted(dead)}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"{OUT}: {len(docs)} documents, {len(pages)} pages, {len(dead)} dead page links")


if __name__ == "__main__":
    main()
