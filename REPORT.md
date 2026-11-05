# D01: Delhi Development Authority public website (dda.gov.in)

**Status:** ✅ COMPLETE. All 3,046 unique pages and 22,746 documents (86.0 GB) that the site delivers are stored. The analysis tables, the eprocure link and the full-text table (21,089 PDFs) are built. Next: decisions on OCR, the privacy indicator and a change watch.
**Updated:** 5 Nov 2026 23:45 CET · **Family:** `dda` · **Code:** `s1d-labs/dda@main` (PRs #3–#7 merged; this report is the last commit, pushed)
**Projects:** `dda-pages` (task `crawl`, target `dda.gov.in`, `proxy=IN`), `dda-docs` (task `crawl`, target `dda.gov.in`, `proxy=IN`)
**Data:** `select … from public.records where project = 'dda-docs'` · organised tables `ws_trideep`, schema `dda` (Metabase "Workspace: trideep") · bucket `dda-docs/docs/sites/default/files/…`, `dda-pages/pages/…` · HTML report [`reports/dda-audit.html`](reports/dda-audit.html)
**Previous report:** first report (scope notes in [`FINDINGS.md`](FINDINGS.md))

---

## Contents
1. [TL;DR](#1-tldr)
2. [Where things stand](#2-where-things-stand)
3. [Pick up here](#3-pick-up-here)
4. [What stands out](#4-what-stands-out)
5. [The source](#5-the-source) · [5.1 Site map](#51-site-map)
6. [How it is collected](#6-how-it-is-collected)
7. [The data](#7-the-data) · [7.1 Fields](#71-fields) · [7.2 What is in it](#72-what-is-in-it) · [7.3 How to query it](#73-how-to-query-it)
8. [Verification](#8-verification)
9. [Known gaps and quality issues](#9-known-gaps-and-quality-issues)
10. [Risks and open decisions](#10-risks-and-open-decisions)
11. [Next steps](#11-next-steps)

---

## 1. TL;DR
- **The scrape is complete:** 3,046 pages and 23,095 unique document links. 22,746 documents are stored, 346 links return HTTP 404 on the site, and 3 files are never delivered by the server.
- **Our own defect, now fixed:** the first crawl missed 395 listing pages (191 of the 285 tender archive pages). That made FY 2022-23 look like 20 tenders; the real count on the site is 512. The repair pass added 397 pages and 3,988 documents.
- **The main finding:** DDA does not publish awards on the central portal. Only 2.0% of its 53,170 eprocure tenders reach the stage "awarded" (IHQ: 30.0%, RCFL: 45.2%). 243 of the 252 eprocure tenders that have an award letter on the DDA site still show "in evaluation" there.
- **PM-UDAY:** 1,205 of 1,731 unauthorised colonies have a final boundary map. The boundary table has no update after 14 Aug 2020.
- **Full text:** 10,524 of 21,089 read PDFs have a text layer and are searchable (`dda.document_text`); "unauthorised colony" matches 1,809 documents.
- **Next (trideep):** the three decisions in [10](#10-risks-and-open-decisions); then read award values from the letters' text.

## 2. Where things stand

| Project | State | Items done / total | Failed · pending · running | Records stored | Pace (24 h) | ETA |
|---|---|--:|--:|--:|--:|---|
| `dda-pages` | ✅ COMPLETE | 3,270 / 3,270 (100.0%) | 0 · 0 · 0 | 3,270 | 3,270 | done |
| `dda-docs` | ✅ COMPLETE | 23,135 / 23,137 (100.0%) | 2 · 0 · 0 | 23,135 | 23,135 | done (2 items stopped at 40 attempts) |

- The queues hold more items than unique URLs: 224 pages and 42 documents are second spellings of one URL (`http`/`https`, space/`%20`, `&amp;`). The tables in `ws_trideep` count each URL once: 3,046 pages, 23,095 documents.
- `dda-docs` records: 22,746 stored files, 346 broken links (HTTP 404), 1 unretrievable (HTTP 403), 2 failed (server cuts the transfer).
- Hub view: pool on, no health probe (on purpose: the hub prober can not do the legacy TLS), not throttled. Uploads: 86.7 GB (`uploaded_bytes`), 22,778 files.
- Runs: 156 `dda-docs` runs (148 finished, 8 failed in the hub outage on 4 Nov), 8 `dda-pages` runs. The pool members' runners did the work (hub dispatch).

## 3. Pick up here
- **Repo:** `~/dda` (branch `main`, clean after this commit) · **Run tests:** `~/.venvs/dda/bin/python -m pytest tests -q` · **Try one item:** `myproxy run python crawl.py --local https://dda.gov.in/whats-new`
- **Next action:** decide [10](#10-risks-and-open-decisions) item 2 (OCR). For the award values, start from `select w.title, t.text from dda.work_awards w join dda.document_text t on t.url = w.doc_url where t.has_text`.
- **Waiting on:** nothing blocking. Decisions in [10](#10-risks-and-open-decisions) (privacy indicator, OCR, change watch) are trideep's.

## 4. What stands out
1. **DDA keeps awards off the central portal.** 1,070 of 53,170 DDA tenders (2.0%) are "awarded" on eprocure; 45,894 (86.3%) stay "in evaluation". Of 252 eprocure tenders with an award letter on `dda.gov.in`, 243 show "in evaluation". A direct check agrees: 14 award letters print the eprocure Tender ID itself (for example `2022_DDA_670807_1`), and all 14 tenders are "in evaluation" on eprocure. *So what:* the award letters on the DDA site (1,504) are the only public award source for most DDA tenders; `dda.award_links` joins them.
2. **The PM-UDAY boundary work stopped in 2020.** `/delineated-boundary` lists 1,716 colonies; final boundary uploads run from 11 Mar 2020 to 14 Aug 2020 only. 152 rows say "can not be delineated as per SOP" (116: "Shapefile of the colony is not available"). 154 of the 1,731 listed colonies are not in the boundary table at all.
3. **A coverage defect looked like a finding.** FY 2022-23 showed 20 tender rows before the repair and 512 after it. The Drupal pager shows a window of links only; one timeout hid 191 archive pages. *Fix:* `discover.py` now queues every page 1..N of a listing.
4. **The server never delivers some files.** `planning files/3_tc_2025_12.12.2025.pdf` stops at 38,797,312 of 40,734,768 bytes on every try; the next connections then fail for a while (a guess: an inline security device on DDA's side, not confirmed). The pool ran about 38 runner jobs an hour (18:00–21:00 CET) to retry 3 such files. *Fix:* `crawl.py` now gives up after 10 tries (`GIVE_UP_AFTER`).
5. **Contractor financial documents are public.** The archive `/contractor-registered-archived` links 2,171 files, among them 543 bank solvency certificates and 541 application forms. Many contractors are sole proprietors. We did not open these files. Also, 73 of 349 award letters with a text layer print a bank account number of the contractor (counted only). *So what:* a privacy indicator to raise with DDA.
6. **Single bids cluster in some divisions.** Since 2022, the electrical division `EE/ELD-4` has 24.8% single-bid tenders on eprocure (125 tenders), `EE/ELD-11` 18.1%; the DDA-wide share is 2.5%–5.1% a year since 2020.
7. **About half the PDFs are scans.** The full run: 10,524 of 21,089 PDFs (49.9%) have a text layer; a random sample of 500 gave 53.0%. Tender notices: 55.9%, but the estimated cost is readable in only 23 of 188 sampled notices. *So what:* take values from eprocure, not from the PDFs; OCR is needed for the other ~47%.
8. **Many files are published more than once.** 1,252 files occur at more than one URL (1,494 extra copies, 2.4 GB); one file has 21 URLs.

## 5. The source
- Publisher: Delhi Development Authority. Site: Drupal, English plus a Hindi mirror under `/hi/`. All scraped content is public; no login, OTP or captcha was used.
- Network: answers only from India (box in Germany and plain GitHub runners time out). Works through the hub's India proxies (`proxy="IN"`) and `myproxy` on the box.
- TLS: needs `OP_LEGACY_SERVER_CONNECT` and the missing GlobalSign GCC R46 OV intermediate (`certs/`); verification stays on (`ddatls.py`).
- Rate limits seen: 37 `http_403` and 40 blocked counts in all runs; no 429. HTTP 404: 608 requests.

### 5.1 Site map
| What | URL / form | Notes |
|---|---|---|
| Listings (tenders, notices, orders, circulars) | `/tenders`, `/archive-tender?page=N`, `/whats-new`, `/public-notices`, … | Drupal views, 10 rows a page; 116 paged listings |
| Files | `/sites/default/files/<folder>/<name>` | 23,095 links; folders `tender` 2,411, `Personnel` 1,819, `pmuday` 1,741 (first discovery) |
| Colony boundaries | `/delineated-boundary` | one HTML table, 1,716 rows, links to boundary PDFs |
| Colony lists | `/pm-uday/list-of-colonies-affluent-colonies` | `1731_uc.pdf` and the list of 69 affluent colonies (text PDF) |
| Contractor archive | `/contractor-registered-archived` | 2,171 files (privacy indicator, item 5) |
| Hindi mirror | `/hi/…` | 598 pages against 2,448 English pages |
| Transactional portals | `eservices.dda.org.in`, `drms.dda.org.in`, `vipreferences.dda.org.in`, `ddalop.org.in` | login and captcha: out of scope |
| Small public portals | `stf.dda.org.in` (13 notices), `ddagreens.dda.org.in/PLantation/` (plantation counts) | not scraped; see [11](#11-next-steps) |

## 6. How it is collected
- **Code:** `discover.py` (breadth-first crawl → `seeds.json`; `--resume --repair`), `crawl.py` (task `crawl`: page parse incl. HTML tables, or document download + upload), `ddatls.py` (TLS session), `family.py` / `setup_family.py` (projects, queues), `build_db.py` (organised tables), `extract_colonies.py`, `link_eprocure.py`, `linkcheck.py`, `pdf_census.py`, `extract_text.py`, `analyze.py` + `report_html.py` (HTML report).
- **Queue:** one item per URL; key `p-`/`d-` + first 20 hex of SHA-1 of the URL as queued. Record id = SHA-1 of the URL, so a re-run replaces the record.
- **Pace & behaviour:** up to 4 workers (the family's India proxy cap), 1 request at a time, ≥ 0.3 s apart. Average 0.51 s to headers per document request, 0.85 s per page (`t_http_s` / `n_http`).
- **Decision (trideep/Claude, 4 Nov 2026):** no health probe, because the hub prober can not do the legacy TLS.
- **Decision (Claude, 5 Nov 2026):** documents stay in the pool; a pages-first pause is now a Setup input (`docs_pool=false`), not a code change, because running workers keep their project until their run ends.

## 7. The data
- Hub: `public.records` for `dda-pages` (3,270) and `dda-docs` (23,135). Raw pages in the bucket as `dda-pages/pages/<path>.html.gz`, files as `dda-docs/docs/<site path>` (`documents.bucket_key` gives the exact key).
- Workspace `ws_trideep`, schema `dda`: 16 tables, largest `document_text` (21,089 rows, 118 MB), `eprocure_tenders` 53,170 rows, `documents` 23,095, `listing_rows` 20,202, `html_tables` 12,354.
- Example document record: `{"url": "https://dda.gov.in/sites/default/files/Housing_Department/corrigendum07012026.pdf", "type": "document", "ext": "pdf", "bytes": 447670, "sha256": "57e18806…"}`

### 7.1 Fields
| Field | Source | Notes |
|---|---|---|
| `documents.status` | record + queue (derived) | `stored`, `broken` (404), `unretrievable`, `failed` |
| `documents.bucket_key` | record (derived) | **depends on the URL as queued**: a space and `%20` give different keys |
| `listing_rows.date` | row text (derived) | **two-digit years** resolve to the past (`86` → 1986) |
| `tenders.nit`, `office`, `fy` | NIT text (derived) | `07/EE/HCD-10/DDA/2026-27` → `EE/HCD-10`, `2026-27`; **FY is null when the two halves are not consecutive** |
| `tender_links.nit_key` | derived | `7|EEELD8|2026-27`; NIQ numbers start with `Q` |
| `colony_boundary_status.boundary_status` | view (derived) | joins the colony list and the boundary table on `reg_key` |
| `document_text.has_text` | `pdftotext` (derived) | false = scan, needs OCR |

### 7.2 What is in it
| Documents | Count |
|---|--:|
| stored | 22,746 |
| broken (HTTP 404) | 346 |
| failed (server cuts transfer) | 2 |
| unretrievable (HTTP 403) | 1 |

| Tender rows on the site by FY | 2020-21 | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 | 2026-27 |
|---|--:|--:|--:|--:|--:|--:|--:|
| rows | 47 | 136 | 512 | 244 | 237 | 376 | 265 |

| Other tables | Rows |
|---|--:|
| work award letters | 1,504 (288 with an NIT) |
| debarment / suspension orders | 39 (+3 withdrawals); 14 of them dated 2025 |
| land acquisition awards | 1,810 (844 with no year in the award number) |
| unauthorised colonies | 1,731 + 69 affluent |

### 7.3 How to query it
```sql
-- boundary status of the PM-UDAY colonies
select boundary_status, count(*) from dda.colony_boundary_status where list = '1731' group by 1 order by 2 desc;
-- a site tender row with its eprocure value and bid count
select t.nit, t.date, e.tender_value, e.bids_count, e.stage_group
from dda.tenders t join dda.tender_links l using (page_url, row_no) join dda.eprocure_tenders e using (tender_id) limit 20;
-- full-text search in the PDF text layer
select url from dda.document_text where to_tsvector('simple', text) @@ plainto_tsquery('simple', 'land pooling');
-- broken links by folder
select folder, count(*) from dda.broken_links group by 1 order by 2 desc;
```

## 8. Verification
- Tests: 31 passed (`~/.venvs/dda/bin/python -m pytest tests -q`, 5 Nov 2026 23:40 CET), also in a venv without `psycopg2`.
- CI: `check` green on PR #7 and on `main` (5 Nov 2026 22:35 CET). One PR run **failed** before that: `tests/test_link.py` imported `psycopg2`, which CI does not install (my mistake, fixed with lazy imports). Runs waited up to an hour in the queue: the org's own `s1d-labs/scrape-runner` holds about 20 jobs; I cancelled 15 redundant queued runs.
- scrape-check: 21 PASS, 1 WARN (no health probe, on purpose), 4 Nov 2026 22:17 CET. Not re-run (it fetches the live site).
- Cross-checks done: every listing pager checked against its last page (0 gaps after the repair); all 22,746 stored files checked in the bucket by HEAD (all present, all sizes match); all failed downloads checked by HEAD (404); colony list 1,731 of 1,731 rows extracted; record ids stable on re-run (upsert by URL hash).
- **Not checked:** the content of scanned PDFs; the 311 site tender rows that do not link to eprocure (format or missing on the portal: not confirmed); the stage data in `eprocure.tender_facts` is as old as the team's last eprocure scrape.

## 9. Known gaps and quality issues
| # | Issue | Size | Impact / what to do |
|---|---|--:|---|
| 1 | **Scanned PDFs** (no text until OCR) | 10,565 of 21,089 read PDFs, plus 614 PDFs over 25 MB not read | OCR later (user decision: no OCR now) |
| 2 | Broken document links (at the source) | 346 | recorded once; listed in `dda.broken_links` |
| 3 | Site tender rows not linked to eprocure (unclear) | 311 of 1,817 | `EE/EMD-7` (53) and `HD-III` (54) have no match on eprocure; check by hand |
| 4 | Award letters without an NIT number (at the source) | 1,216 of 1,504 | can only link by text; needs PDF text |
| 5 | Land acquisition awards without a year (at the source) | 844 of 1,810 | year only in the PDF |
| 6 | Internal page links that return 404 (at the source) | 76 | none |
| 7 | Files the server never delivers (at the source) | 3 | recorded; no more retries |
| 8 | Hindi mirror smaller than English (at the source) | 522 of 2,448 English pages (21.3%) have a Hindi page at the same path | lower bound: a Hindi page may use another path; `personnel` 9 of 158 |
| 9 | eprocure tenders with a future `published_at` (team data) | 67 of 53,170 | tell the eprocure family owner |
| 10 | Second spellings in the hub queue (missed by us, fixed) | 224 pages, 42 docs | harmless; tables count each URL once |

## 10. Risks and open decisions
- **Risks:** running `build_db.py` alone drops `tender_links` and `award_links`; run `link_eprocure.py` after it. Running Setup again is safe: `seed_queue` keeps existing keys and adds only new ones. `extract_text.py` reads files from the bucket (B2 egress); keep it in bounded runs.
- **To decide (trideep):**
  1. Raise the contractor-documents privacy indicator with DDA? Recommendation: yes, as an indicator only, with counts.
  2. OCR of the ~10,000 scanned PDFs: now or later? Recommendation: later, starting with Authority agendas and land acquisition awards.
  3. A weekly change watch (re-run discovery, seed only new keys)? Recommendation: yes; it costs a few hundred requests a week.

## 11. Next steps
**To do now**
1. Read the award amount and date from the 349 award letters with text; join to `dda.eprocure_tenders` by `dda.award_links`.
2. Read the 614 PDFs over 25 MB for text: `extract_text.py` with a higher `MAX_BYTES` (most are scans).
3. After any rebuild: `python build_db.py --html DIR && python link_eprocure.py && python analyze.py && python report_html.py analysis.json reports/dda-audit.html`.

**To decide**
4. The three decisions in [10](#10-risks-and-open-decisions).

**Later**
5. Read award date and value from the award letters' text and join them to `dda.eprocure_tenders` (fills the award gap of item 1 in [4](#4-what-stands-out)).
6. Check 20 of the 311 unlinked tender rows by hand on eprocure (start with `EE/EMD-7` and `HD-III`).
7. OCR pilot on `Authority Meeting` agendas (about 470 files, 1959 to now).
8. Scrape the small public portals `stf.dda.org.in` and `ddagreens.dda.org.in` (a new project each, a few pages).
9. Hindi parity by title, not only by path (the path check in [9](#9-known-gaps-and-quality-issues) is a lower bound).

**Housekeeping**
10. CI: the org runner queue blocks `check`; ask the hub owner whether `s1d-labs/scrape-runner` can leave free slots.
11. `~/redispatch-dda-scrape.sh` and `~/redispatch-dda-scrape.log` are no longer needed (the hub dispatches); delete them when you agree.
