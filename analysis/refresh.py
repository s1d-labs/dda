"""Rebuild everything after new scrape data, in the right order (box only).

    eval "$(mybucket env)"                                  # read-only bucket key (for --sync)
    python -m analysis.refresh --html /tmp/dda-html --sync  # sync raw pages, then all steps below

Steps: build_db (tables) -> link_eprocure (tender and award links) -> extract_awards (award values) ->
analyze (figures) -> report_html (reports/dda-audit.html). extract_colonies, extract_text and pdf_census are
separate, slower steps; build_db keeps their tables.
"""
import argparse
import os
import subprocess
import sys

STEPS = [
    ["analysis.build_db", "--html", "{html}"],
    ["analysis.link_eprocure"],
    ["analysis.extract_awards"],
    ["analysis.analyze", "--out", "reports/analysis.json"],
    ["analysis.report_html", "reports/analysis.json", "reports/dda-audit.html"],
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True, help="local mirror of the bucket's dda-pages/pages/")
    ap.add_argument("--sync", action="store_true", help="first sync the mirror from the bucket (needs mybucket env)")
    args = ap.parse_args()
    if args.sync:
        cmd = ["aws", "s3", "sync", "s3://s1d-labs-trideep/dda-pages/pages", args.html, "--only-show-errors"]
        if os.environ.get("AWS_ENDPOINT_URL"):
            cmd += ["--endpoint-url", os.environ["AWS_ENDPOINT_URL"]]
        subprocess.run(cmd, check=True)
    for step in STEPS:
        argv = [sys.executable, "-m"] + [a.format(html=args.html) for a in step]
        print("==>", " ".join(argv[2:]), flush=True)
        subprocess.run(argv, check=True)


if __name__ == "__main__":
    main()
