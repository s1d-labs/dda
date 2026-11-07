"""Award values from the text of DDA award letters: estimated cost, tendered (awarded) amount, letter date.

eprocure shows only 2% of DDA tenders as awarded. The award letters on dda.gov.in say what was awarded. About a
quarter of them have a text layer (dda.document_text, from extract_text.py); the text is often an old OCR layer,
so labels and amounts are out of order. The rules:

  - an amount is 'Rs. 1,10,37,523/-', 'Rs.643720/', or an Indian-grouped number '25,50,671.00' (no account
    numbers: a plain number needs 'Rs' and at most 10 digits);
  - each label ('Estimated cost', 'Estt. Cost' / 'Tendered amount', 'Quoted % Tender Amount', 'contract amount')
    takes the nearest amount after it, else just before it, and never an amount next to FDR / PG / EMD /
    performance guarantee / earnest money;
  - the check: the estimated cost against the eprocure tender value of the linked tender (dda.award_links or the
    Tender ID printed in the letter), and tendered / estimated between 0.3 and 1.6.

    python -m analysis.extract_awards               # -> ws_$USER: dda.award_values

No names: the table holds amounts, dates and keys only.
"""
import argparse
import os
import re

import crawl

AMOUNT = re.compile(r"(?:(?:Rs\.?|₹|INR)\s*:?\s*(\d{4,10}(?:\.\d{1,2})?)(?![\d,])"
                    r"|(\d{1,3}(?:,\d{2})*,\d{3}(?:\.\d{1,2})?)(?![\d,]))", re.I)
EST = re.compile(r"estimated\s+cost|estt?\.?\s*cost|estimate\s+cost", re.I)
TND = re.compile(r"tender(?:ed)?\s+am(?:o|n)+unt|quoted\s*%?\s*(?:tender\s*)?am(?:o|n)+unt|contract\s+(?:amount|value)|"
                 r"agreement\s+amount|awarded\s+amount|(?:negotiated\s*(?:and|&|/)\s*)?accepted\s*(?:/\s*negotiated\s*)?"
                 r"(?:amount|rate)", re.I)
# '43.10 % (Forty Three ...) below the estimated cost' (a % against DSR is a different base: not used)
PCT = re.compile(r"(\d{1,2}(?:\.\d{1,2})?)\s*%\s*(?:\([^)]{0,60}\)\s*)?(below|above)\s*(?:the\s*)?estimated\s+cost", re.I)
NOT = re.compile(r"F\.?D\.?R|\bPG\b|perform|guarantee|E\.?M\.?D|earnest|security|A/?c\.?\s*No|processing", re.I)
DATED = re.compile(r"dated?\s*[:.\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\s?\d{2,4})", re.I)
TENDER_ID = re.compile(r"(20\d{2})_?DDA_?(\d{5,7})_(\d)", re.I)


def amounts(text):
    """[(start, end, rupees)] of every amount in the text, with the 50 characters before it free of FDR/PG/EMD."""
    out = []
    for m in AMOUNT.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        if v < 1000:
            continue
        before = text[max(0, m.start() - 50):m.start()]
        out.append((m.start(), m.end(), v, bool(NOT.search(before))))
    return out


def value_after(label_rx, text, amts, window=160):
    """The amount nearest after the label (else nearest before, within 60 characters); None if no label."""
    best = None
    for lm in label_rx.finditer(text):
        after = [a for a in amts if 0 <= a[0] - lm.end() <= window and not a[3]]
        if after:
            cand = min(after, key=lambda a: a[0] - lm.end())
        else:
            before = [a for a in amts if 0 <= lm.start() - a[1] <= 60 and not a[3]]
            cand = max(before, key=lambda a: a[1]) if before else None
        if cand and best is None:
            best = cand[2]
    return best


def parse_letter(text):
    """(letter_date, estimated_rs, tendered_rs, tender_id) from the text of one award letter."""
    text = text or ""
    amts = amounts(text)
    est, tnd = value_after(EST, text, amts), value_after(TND, text, amts)
    if est and tnd and tnd == est:
        tnd = None
    if est and not tnd:
        p = PCT.search(text)
        if p:
            pct = float(p.group(1)) / 100
            tnd = round(est * (1 - pct if p.group(2).lower() == "below" else 1 + pct), 2)
    d = DATED.search(text[:1500])
    date = crawl.iso_date(d.group(1)) if d else None
    tid = TENDER_ID.search(re.sub(r"\s", "", text))
    tender_id = f"{tid.group(1)}_DDA_{tid.group(2)}_{tid.group(3)}" if tid else None
    return date, est, tnd, tender_id


def main():
    import psycopg2
    import psycopg2.extras
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ws_" + os.environ.get("USER", "trideep"))
    args = ap.parse_args()
    conn = psycopg2.connect(dbname=args.db, host="127.0.0.1")
    with conn, conn.cursor() as cur:
        cur.execute("""select w.page_url, w.row_no, w.doc_url, w.date, t.text,
                              (select l.tender_id from dda.award_links l where l.page_url = w.page_url
                               and l.row_no = w.row_no order by l.tender_id limit 1)
                       from dda.work_awards w join dda.document_text t on t.url = w.doc_url where t.has_text""")
        rows = cur.fetchall()
        cur.execute("select tender_id, tender_value, stage_group from dda.eprocure_tenders")
        ep = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
        out = []
        for page_url, row_no, doc_url, row_date, text, linked in rows:
            date, est, tnd, tid = parse_letter(text)
            tender_id = tid if tid in ep else linked
            ep_value, ep_stage = ep.get(tender_id, (None, None))
            ratio = round(tnd / est, 3) if est and tnd else None
            checks = []
            if ratio is not None:
                checks.append("ratio ok" if 0.3 <= ratio <= 1.6 else "ratio out of range")
            if est and ep_value:
                checks.append("estimate = eprocure value" if abs(est - float(ep_value)) <= 0.02 * float(ep_value)
                              else "estimate differs from eprocure")
            out.append((page_url, row_no, doc_url, date or row_date, est, tnd, ratio, tender_id,
                        "letter" if tid in ep else ("nit" if linked else None), ep_value, ep_stage,
                        "; ".join(checks) or None))
        cur.execute("""DROP TABLE IF EXISTS dda.award_values;
            CREATE TABLE dda.award_values (page_url text, row_no int, doc_url text, letter_date date,
              estimated_rs numeric, tendered_rs numeric, ratio numeric, tender_id text, tender_id_from text,
              eprocure_value numeric, eprocure_stage text, checks text, PRIMARY KEY (page_url, row_no))""")
        psycopg2.extras.execute_values(cur, "INSERT INTO dda.award_values VALUES %s ON CONFLICT DO NOTHING", out)
        cur.execute("""select count(*), count(estimated_rs), count(tendered_rs), count(tender_id),
                       count(*) filter (where checks like '%estimate = eprocure value%'),
                       count(*) filter (where checks like '%ratio ok%') from dda.award_values""")
        print("letters, with estimate, with tendered amount, with tender, estimate matches eprocure, ratio ok:",
              cur.fetchone())
    conn.close()


if __name__ == "__main__":
    main()
