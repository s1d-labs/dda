"""Full text of the stored PDFs that have a text layer (no OCR), for full-text search.

Reads each stored PDF from the bucket (read-only key), runs `pdftotext` (poppler) on the first pages and
stores the text in the workspace database. Scanned PDFs give almost no text; they are marked
has_text = false and left for OCR later. Resumable: documents already done are skipped.

    eval "$(mybucket env)"
    python -m analysis.extract_text --max-minutes 60          # a bounded portion; run again to continue

Table dda.document_text (url, bucket_key, folder, pages, chars, has_text, text, extracted_at) with a
full-text index. Search:  select url from dda.document_text
                          where to_tsvector('simple', text) @@ plainto_tsquery('simple', 'land pooling');
"""
import argparse
import os
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import psycopg2
import psycopg2.extras

BUCKET = "s1d-labs-trideep"
PRIORITY = ["tender", "public-notice", "notice", "pmuday", "Landmgmt", "LandDisposal", "land-pooling",
            "gazette-notification", "planning files", "Housing_Department", "Housing Department", "Engineering",
            "Personnel", "Accounts", "RTI", "technical_committee", "MinutesTechnicalCommittee"]
MAX_BYTES = 25_000_000
MAX_PAGES = 40
MAX_CHARS = 300_000

DDL = """CREATE TABLE IF NOT EXISTS dda.document_text (
  url text PRIMARY KEY, bucket_key text, folder text, pages int, chars int, has_text bool, text text,
  extracted_at timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS document_text_fts ON dda.document_text USING gin (to_tsvector('simple', coalesce(text, '')));"""


def todo(cur, limit):
    cur.execute("""select d.url, d.bucket_key, d.folder from dda.documents d
                   left join dda.document_text t using (url)
                   where d.status = 'stored' and d.ext = 'pdf' and d.bucket_key is not null and t.url is null
                     and d.bytes between 1000 and %s
                   order by array_position(%s::text[], d.folder) nulls last, d.bytes
                   limit %s""", (MAX_BYTES, PRIORITY, limit))
    return cur.fetchall()


def extract(s3, row, tmpdir):
    url, key, folder = row
    try:
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        path = os.path.join(tmpdir, f"{abs(hash(url))}.pdf")
        with open(path, "wb") as f:
            f.write(body)
        try:
            info = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=30).stdout
            pages = int(next((l.split()[-1] for l in info.splitlines() if l.startswith("Pages:")), "0") or 0)
            out = subprocess.run(["pdftotext", "-l", str(MAX_PAGES), "-enc", "UTF-8", path, "-"],
                                 capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
        finally:
            os.unlink(path)
    except Exception as e:  # noqa: BLE001 - a damaged file is a result
        return (url, key, folder, None, 0, False, f"[error: {type(e).__name__}]")
    text = " ".join(out.split())[:MAX_CHARS].replace("\x00", "")
    per_page = len(text) / max(1, min(pages or 1, MAX_PAGES))
    return (url, key, folder, pages, len(text), per_page >= 25, text if per_page >= 25 else None)


def main():
    import boto3
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    ap.add_argument("--max-minutes", type=float, default=60)
    ap.add_argument("--threads", type=int, default=3)
    args = ap.parse_args()
    s3 = boto3.client("s3", endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
    conn = psycopg2.connect(dbname=args.db, host="127.0.0.1")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(DDL)
    stop = time.time() + args.max_minutes * 60
    done = with_text = 0
    with tempfile.TemporaryDirectory(prefix="dda_text_") as tmpdir, ThreadPoolExecutor(args.threads) as ex:
        while time.time() < stop:
            batch = todo(cur, 60)
            if not batch:
                break
            rows = list(ex.map(lambda r: extract(s3, r, tmpdir), batch))
            psycopg2.extras.execute_values(cur, """INSERT INTO dda.document_text
                (url, bucket_key, folder, pages, chars, has_text, text) VALUES %s ON CONFLICT (url) DO NOTHING""", rows)
            done += len(rows)
            with_text += sum(1 for r in rows if r[5])
            print(f"{done} done, {with_text} with text, last folder {batch[-1][2]}", flush=True)
    cur.execute("select count(*), count(*) filter (where has_text) from dda.document_text")
    print("table:", cur.fetchone())


if __name__ == "__main__":
    main()
