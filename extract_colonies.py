"""Unauthorised colonies of Delhi as a table, from the PM-UDAY lists DDA publishes.

Inputs (text PDFs, no OCR): the list of 1,731 unauthorised colonies (excluding affluent ones),
pmuday/1731_uc.pdf, and the list of 69 colonies inhabited by the affluent section of society.
The pool stores both in the bucket (dda-docs/docs/sites/default/files/pmuday/...).

    mybucket get dda-docs/docs/sites/default/files/pmuday/1731_uc.pdf DIR/
    python extract_colonies.py --uc DIR/1731_uc.pdf --affluent DIR/69.pdf      # -> ws_$USER dda.unauthorised_colonies
    python extract_colonies.py ... --csv data/unauthorised_colonies.csv

Output columns: list ('1731' or 'affluent'), sl_no, reg_no (as printed), part, reg_key (one form for
joins, e.g. '732B', '90-ELD'), name, pin (Delhi 1100xx from 'Delhi-41' where printed).
build_db.py's delineated_boundaries joins on reg_key (view dda.colony_boundary_status).
"""
import argparse
import csv
import os
import re

SL_RX = re.compile(r"^\s*(\d{1,4})\.?\s*$")
TEXT_ROW_RX = re.compile(r"^(\d{1,4})\.\s+(\d{1,4}(?:\s*-\s*\(?[A-Z]{2,4}\)?)?)(?:\s+([A-Z]))?(?:\s+(.*))?$")
PIN_RX = re.compile(r"Delhi\s*[-,]?\s*(?:1100)?(\d{2})\b", re.I)


def reg_key(reg, part=""):
    """One form of a colony registration number for joins: 'REGD. No.732 B' -> '732B',
    '90-(ELD)' / '90ELD' -> '90-ELD', '08LOP' -> '8-LOP', '1476_B' -> '1476B'."""
    t = re.sub(r"(?i)regd?\.?\s*no\.?", "", f"{reg or ''}{part or ''}")
    t = re.sub(r"[^0-9A-Za-z]", "", t).upper()
    m = re.fullmatch(r"0*(\d+)(ELD|LOP)?([A-Z]?)", t)
    if not m:
        return t or None
    return m.group(1) + (f"-{m.group(2)}" if m.group(2) else "") + m.group(3)


def pin_of(name):
    m = PIN_RX.search(name or "")
    if not m:
        return None
    n = int(m.group(1))
    return f"1100{n:02d}" if 1 <= n <= 99 else None


def clean(s):
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def from_pdf(path, columns):
    """Rows from the bordered tables; the first row of each page has no top border, so pdfplumber
    misses it: those are read from the page text instead."""
    import pdfplumber
    got = {}
    with pdfplumber.open(path) as pdf:
        texts = []
        for pg in pdf.pages:
            texts.append(pg.extract_text() or "")
            for t in pg.extract_tables():
                for r in t:
                    m = SL_RX.match(r[0] or "")
                    if m:
                        got[int(m.group(1))] = dict(zip(columns, [clean(c) for c in r[1:]]))
    top = max(got) if got else 0
    for text in texts:
        lines = [x.strip() for x in text.splitlines()]
        for i, line in enumerate(lines):
            m = TEXT_ROW_RX.match(line)
            split = re.match(r"^(\d{1,4})\.\s+(\D.*)$", line)
            if (not m and split and 0 < i < len(lines) - 1 and int(split.group(1)) not in got
                    and re.fullmatch(r"\d{1,4}-", lines[i - 1]) and re.fullmatch(r"\(?[A-Z]{2,4}\)?", lines[i + 1])):
                # the registration number is split around the name: '120-' / '1558. name' / '(ELD)'
                got[int(split.group(1))] = {"reg_no": lines[i - 1] + lines[i + 1], "part": "",
                                            "name": clean(split.group(2))}
                continue
            if not m or int(m.group(1)) in got or int(m.group(1)) > top + 1:
                continue
            name = m.group(4) or ""
            if not name:     # a wrapped name: one line above the serial line, one line below
                before = lines[i - 1] if i > 0 and not TEXT_ROW_RX.match(lines[i - 1]) else ""
                after = lines[i + 1] if i + 1 < len(lines) and not TEXT_ROW_RX.match(lines[i + 1]) else ""
                name = f"{before} {after}"
            got[int(m.group(1))] = {"reg_no": m.group(2), "part": m.group(3) or "", "name": clean(name)}
    return got


def rows(uc_pdf, affluent_pdf):
    out = []
    if uc_pdf:
        for sl, r in sorted(from_pdf(uc_pdf, ["reg_no", "part", "name"]).items()):
            out.append({"list": "1731", "sl_no": sl, "reg_no": r.get("reg_no", ""), "part": r.get("part", ""),
                        "name": r.get("name", "")})
    if affluent_pdf:
        for sl, r in sorted(from_pdf(affluent_pdf, ["reg_no", "name"]).items()):
            out.append({"list": "affluent", "sl_no": sl, "reg_no": r.get("reg_no", ""), "part": "",
                        "name": r.get("name", "")})
    for r in out:
        r["reg_no"] = clean(r["reg_no"])
        r["reg_key"] = reg_key(r["reg_no"], r["part"])
        r["pin"] = pin_of(r["name"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uc", help="1731_uc.pdf")
    ap.add_argument("--affluent", help="list of 69 affluent colonies (pdf)")
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    ap.add_argument("--csv")
    args = ap.parse_args()
    data = rows(args.uc, args.affluent)
    by_list = {}
    for r in data:
        by_list[r["list"]] = by_list.get(r["list"], 0) + 1
    print("colonies:", by_list)
    cols = ["list", "sl_no", "reg_no", "part", "reg_key", "name", "pin"]
    if args.csv:
        os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows({k: r[k] for k in cols} for r in data)
    if args.db:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(dbname=args.db, host="127.0.0.1")
        with conn, conn.cursor() as cur:
            cur.execute("""CREATE SCHEMA IF NOT EXISTS dda;
                DROP TABLE IF EXISTS dda.unauthorised_colonies CASCADE;
                CREATE TABLE dda.unauthorised_colonies (list text, sl_no int, reg_no text, part text, reg_key text,
                  name text, pin text, PRIMARY KEY (list, sl_no));""")
            psycopg2.extras.execute_values(cur, "INSERT INTO dda.unauthorised_colonies VALUES %s",
                                           [tuple(r[k] for k in cols) for r in data])
            cur.execute("SELECT to_regclass('dda.delineated_boundaries') IS NOT NULL")
            if cur.fetchone()[0]:
                from build_db import COLONY_VIEW
                cur.execute(COLONY_VIEW)
        conn.close()


if __name__ == "__main__":
    main()
