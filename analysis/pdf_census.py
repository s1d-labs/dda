"""How many stored PDFs have a text layer, and how many are scans that need OCR later?

Reads a random sample of stored PDFs from the bucket (read-only key), opens the first pages with pdfplumber
and counts the characters. A page with fewer than 25 characters counts as a scanned page. No OCR is done.

    eval "$(mybucket env)"                      # read-only bucket key
    python -m analysis.pdf_census --sample 400           # -> pdf_census.json (+ per-folder estimate)

For tender notices (NIT) it also tries to read the estimated cost and the earnest money (EMD) from the
text, to measure how much value data the PDFs hold. Output has no names of persons.
"""
import argparse
import io
import json
import os
import random
import re
import subprocess
import time
from collections import Counter, defaultdict

import crawl

BUCKET = "s1d-labs-trideep"
MAX_BYTES = 15_000_000           # skip very large files in the sample (they are mostly scans anyway)
PAGES = 2
AMOUNT = r"(?:Rs\.?|INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore|cr)?"
COST_RX = re.compile(r"estimated\s+cost[^\n\d₹R]{0,60}" + AMOUNT, re.I)
EMD_RX = re.compile(r"(?:earnest\s+money|E\.?M\.?D\.?)[^\n\d₹R]{0,60}" + AMOUNT, re.I)


def rupees(num, unit):
    v = float(num.replace(",", ""))
    unit = (unit or "").lower()
    return v * 1e5 if unit in ("lakh", "lac") else v * 1e7 if unit in ("crore", "cr") else v


def sample_rows(db, n, folder_like=None, seed=7):
    where = "status='stored' and ext='pdf' and bytes between 1000 and %d" % MAX_BYTES
    if folder_like:
        where += f" and folder ilike '{folder_like}'"
    out = subprocess.run(["psql", db, "-tAF", "\t", "-c",
                          f"select bucket_key, folder, bytes from dda.documents where {where} and bucket_key is not null"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    rows = [line.split("\t") for line in out if line]
    random.Random(seed).shuffle(rows)
    return rows[:n], len(rows)


def text_of(pdf_bytes):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        n_pages = len(pdf.pages)
        texts = [(p.extract_text() or "") for p in pdf.pages[:PAGES]]
    return n_pages, texts


def main():
    import boto3
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    ap.add_argument("--sample", type=int, default=400)
    ap.add_argument("--tenders", type=int, default=80, help="extra sample from the tender folder")
    ap.add_argument("--out", default="data/pdf_census.json")
    args = ap.parse_args()
    s3 = boto3.client("s3", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
    rows, population = sample_rows(args.db, args.sample)
    trows, tpop = sample_rows(args.db, args.tenders, "tender", seed=11)
    result = {"population_pdfs": population, "tender_pdfs": tpop, "files": []}
    t0 = time.time()
    for which, (url, folder, size) in [("main", r) for r in rows] + [("tender", r) for r in trows]:
        key = url                    # the bucket key (dda.documents.bucket_key)
        try:
            body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            n_pages, texts = text_of(body)
        except Exception as e:  # noqa: BLE001 - a damaged PDF is a result
            result["files"].append({"sample": which, "folder": folder, "bytes": int(size), "error": type(e).__name__})
            continue
        chars = [len(t.strip()) for t in texts]
        joined = "\n".join(texts)
        rec = {"sample": which, "folder": folder, "bytes": int(size), "pages": n_pages, "chars": chars,
               "text_layer": any(c >= 25 for c in chars), "hindi": bool(re.search(r"[ऀ-ॿ]", joined)),
               }
        if folder == "tender":
            c, e = COST_RX.search(joined), EMD_RX.search(joined)
            rec["cost_rs"] = rupees(*c.groups()) if c else None
            rec["emd_rs"] = rupees(*e.groups()) if e else None
        result["files"].append(rec)
    files = result["files"]
    ok = [f for f in files if "error" not in f]
    main_ok = [f for f in ok if f["sample"] == "main"]
    by_folder = defaultdict(lambda: [0, 0])
    for f in main_ok:
        by_folder[f["folder"]][0] += 1
        by_folder[f["folder"]][1] += f["text_layer"]
    tend = [f for f in ok if f["folder"] == "tender"]
    result["summary"] = {
        "sampled": len(files), "errors": len(files) - len(ok), "seconds": round(time.time() - t0),
        "text_layer_share": round(sum(f["text_layer"] for f in main_ok) / max(1, len(main_ok)), 3),
        "hindi_share": round(sum(f["hindi"] for f in main_ok) / max(1, len(main_ok)), 3),
        "median_pages": sorted(f["pages"] for f in main_ok)[len(main_ok) // 2] if main_ok else None,
        "tender_text_share": round(sum(f["text_layer"] for f in tend) / max(1, len(tend)), 3),
        "tender_cost_found": sum(1 for f in tend if f.get("cost_rs")),
        "tender_emd_found": sum(1 for f in tend if f.get("emd_rs")),
        "tender_sampled": len(tend),
        "by_folder": {k: {"sampled": v[0], "text": v[1]} for k, v in sorted(by_folder.items(), key=lambda kv: -kv[1][0])},
        "error_kinds": dict(Counter(f["error"] for f in files if "error" in f)),
    }
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    print(json.dumps(result["summary"], indent=1)[:3000])


if __name__ == "__main__":
    main()
