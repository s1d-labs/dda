# D01: Delhi Development Authority public website and portals (dda.gov.in)

**Status:** ✅ COMPLETE. All 5 projects are done: 3,046 pages, 22,755 stored documents (86 GB), 338 STF files, 1,916 DDA Greens API calls. A weekly watch now adds new tenders and notices by itself.
**Updated:** 7 Nov 2026 20:40 CET · **Family:** `dda` · **Code:** `s1d-labs/dda@main` (PRs #3–#9 merged; this report arrives with PR #10)
**Projects:** `dda-pages`, `dda-docs`, `dda-watch` (target `dda.gov.in`, `proxy=IN`) · `dda-stf` (`stf.dda.org.in`), `dda-greens` (`ddagreens.dda.org.in`), no proxy
**Data:** `select … from public.records where project = 'dda-docs'` · tables `ws_trideep`, schema `dda` (Metabase "Workspace: trideep") · bucket `dda-docs/`, `dda-pages/`, `dda-stf/`, `dda-watch/` · HTML report [`reports/dda-audit.html`](reports/dda-audit.html)
**Previous report:** 5 Nov 2026 23:45 CET (this file, earlier version)

---

## Contents
1. [TL;DR](#1-tldr)
2. [Where things stand](#2-where-things-stand) · [2.1 Changes since last report](#21-changes-since-last-report)
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
- **Everything is scraped.** dda.gov.in (3,046 pages, 22,755 files), the Special Task Force portal (165 agendas, 170 minutes, 3 quarterly minutes) and DDA Greens (638 parks). No queue item is open.
- **Award data now exists.** eprocure shows only 2.0% of DDA's 53,170 tenders as awarded. We read the award letters on the DDA site: 212 of 349 letters with text give the awarded amount. The median award is **0.66 times** the estimate; 104 of 189 are below 70%.
- **Link to eprocure:** 1,730 of 1,837 site tender rows (94.2%) and 281 of 288 award letters link to their eprocure tender. 285 of 299 linked tenders with an award letter still show "in evaluation" on eprocure.
- **DDA Greens:** the species of 83.7% of planted trees is "Other", and 0 of 52,955 plantation photos have a verified location.
- **Next (trideep):** decide on OCR (about 10,500 scanned PDFs) and on raising the privacy indicator with DDA ([10](#10-risks-and-open-decisions)).

## 2. Where things stand

| Project | State | Items done / total | Failed · pending · running | Pace (24 h) | ETA |
|---|---|--:|--:|--:|---|
| `dda-pages` | ✅ COMPLETE | 3,270 / 3,270 | 0 · 0 · 0 | 0 | done |
| `dda-docs` | ✅ COMPLETE | 23,137 / 23,137 | 0 · 0 · 0 | 2 | done |
| `dda-stf` | ✅ COMPLETE | 345 / 345 | 0 · 0 · 0 | 345 | done |
| `dda-greens` | ✅ COMPLETE | 1,916 / 1,916 | 0 · 0 · 0 | 1,916 | done |
| `dda-watch` | ⏳ RUNNING (weekly) | 1 / 1 (week 2026-W45) | 0 · 0 · 0 | 1 | next: Mon 9 Nov 02:30 UTC |

- `dda-docs`: 22,755 stored, 346 broken links (HTTP 404), 3 unretrievable (the server never delivers them). The 2 items that kept failing were closed on 7 Nov with a one-time `reset_failed`; no retry jobs since.
- The queues hold second spellings of some URLs (224 pages, 42 documents); the tables count each URL once.
- Hub: no health probe (on purpose, legacy TLS), not throttled. The hub starts pool runners by itself.

### 2.1 Changes since last report
| | 5 Nov 2026 | 7 Nov 2026 | Change |
|---|--:|--:|---|
| Projects | 2 | 5 | + `dda-stf`, `dda-greens`, `dda-watch` |
| Stored documents (dda.gov.in) | 22,746 | 22,755 | +9 from the first weekly watch |
| Site tender rows linked to eprocure | 1,506 (82.0%) | 1,730 (94.2%) | office spellings normalised |
| Award letters linked | 244 | 281 | |
| Award letters with an awarded amount | 0 | 212 | new: `dda.award_values` |
| Failed `dda-docs` items | 2 | 0 | closed as unretrievable |
| Tests | 31 | 40 | |

## 3. Pick up here
- **Repo:** `~/dda` (branch `main`, clean) · **Run tests:** `python -m pytest tests -q` · **Try one item:** `myproxy run python crawl.py --local https://dda.gov.in/whats-new`
- **Next action:** after each Monday watch, refresh: `eval "$(mybucket env)"; python -m analysis.refresh --html /tmp/dda-html --sync`
- **Waiting on:** decisions in [10](#10-risks-and-open-decisions) (trideep).

## 4. What stands out
1. **DDA awards are not on the central portal.** 1,070 of 53,170 DDA tenders (2.0%) are "awarded" on eprocure (IHQ 30.0%, RCFL 45.2%). 285 of 299 eprocure tenders that have a DDA award letter show "in evaluation"; 14 letters print the eprocure Tender ID and all 14 are "in evaluation". *So what:* `dda.award_values` is the only public award source for these tenders.
2. **Awards far below the estimate.** Median awarded/estimate is 0.66 (189 letters); 27 letters at 0.4–0.5, 44 at 0.5–0.6. In 22 of 34 checked letters the estimate equals the eprocure tender value. *So what:* an indicator of inflated estimates or abnormally low bids; check with the full tender text.
3. **PM-UDAY boundaries stopped in 2020.** 1,205 of 1,731 colonies have a final boundary map; all uploads are from 11 Mar to 14 Aug 2020; 135 are "can not be delineated as per SOP".
4. **DDA Greens figures can not be verified.** 100,147 of 119,627 planted trees (83.7%) and 662,513 of 1,950,038 shrubs (34.0%) have the species "Other". `locationVerified` is 0 of 52,955 photos. 463 parks report ≥ 100% of target, 112 report < 25%.
5. **Contractor financial data is public.** 543 bank solvency certificates and 541 application forms in the contractor archive; 73 of 349 award letters with text print a bank account number (counted only).
6. **STF record:** 166 meetings, agendas from meeting 51, minutes from meeting 1; files uploaded 23 Jan 2020 to 7 Oct 2026; 83 of them on 23 Jan 2020 (a bulk upload of the older meetings).

## 5. The source
- Publisher: Delhi Development Authority. dda.gov.in is a Drupal site with a Hindi mirror; it answers only from India and needs legacy TLS plus a missing intermediate certificate (`ddatls.py`, verification on).
- stf.dda.org.in (ASP.NET; menu postbacks lead to plain `.aspx` pages) and ddagreens.dda.org.in (JSON API) answer from anywhere.
- No login, OTP or captcha is used. Rate limits seen: a few HTTP 403; one server that cuts some transfers.

### 5.1 Site map
| What | URL / form | Notes |
|---|---|---|
| Listings | `/tenders`, `/archive-tender?page=N`, `/whats-new`, … | 116 paged listings, 10 rows a page |
| Files | `/sites/default/files/<folder>/<name>` | 23,095 links |
| Colony boundaries | `/delineated-boundary` | one HTML table, 1,716 rows |
| STF meetings | `stf.dda.org.in/STF-Meeting-Agenda-Title.aspx`, `/Minuts-Of-Meeting-Of-STF-Title-New.aspx` | 335 PDF files |
| Greens API | `ddagreens.dda.org.in/api/plantation/dashboard`, `/filter/parks`, `/Plantation/park-summary?parkId=`, `/plantation/species-summary?parkId=&speciesType=` | officer endpoints left out |
| Login portals | `eservices.dda.org.in`, `drms.dda.org.in`, `vipreferences.dda.org.in`, … | out of scope |

## 6. How it is collected
- **Code:** `crawl.py` (task `crawl`), `watch.py` (task `watch`), `portals.py` (task `portal`, plus `discover`), `discover.py`, `family.py` / `setup_family.py`, `seed_watch.py`; analysis in `analysis/` (see README).
- **Queue:** one item per URL or API call; keys `p-`, `d-`, `s-`, `f-`, `g-` + 20 hex of SHA-1; the watch key is `watch-<ISO week>`.
- **Pace:** dda.gov.in 4 workers (proxy cap), STF 1 worker 800 ms apart, Greens 2 workers 300 ms apart, watch 1 worker (about 130 requests).
- **Decision (Claude, 7 Nov 2026):** files that the server never delivers are recorded as unretrievable after 10 tries (`GIVE_UP_AFTER`).
- **Decision (Claude, 7 Nov 2026):** STF officer lists and Greens officer/plantation details are not scraped (personal data).

## 7. The data
- Hub: `public.records` for the 5 projects. Bucket: raw pages `dda-pages/pages/…`, files `dda-docs/docs/…`, STF files `dda-stf/docs/…`.
- Workspace `ws_trideep`, schema `dda`: 27 tables and views; largest `document_text` (21,089 rows), `eprocure_tenders` (53,170), `documents` (23,104 incl. watch).

### 7.1 Fields
| Field | Source | Notes |
|---|---|---|
| `award_values.tendered_rs` | award letter text (derived) | **noisy OCR layer**; `checks` says if the ratio and the eprocure value agree |
| `tender_links.match` | derived | `key` or `office token` (probable match, one candidate) |
| `tender_unlinked.reason` | derived | `not found on eprocure` / `no key` / `several possible matches` |
| `stf_documents.uploaded` | file name (derived) | first 8 digits are ddmmyyyy |
| `greens_species.plant_name` | API | **"Other" for most trees** |
| `documents.bucket_key` | record | depends on the URL as queued (space vs `%20`) |

### 7.2 What is in it
| Table | Rows |
|---|--:|
| `pages` / `documents` | 3,046 / 23,104 |
| `tenders` / `work_awards` / `debarments` | 1,919 / 1,504 / 42 |
| `award_values` (amount found) | 349 (212) |
| `land_acq_awards` | 1,810 |
| `unauthorised_colonies` | 1,800 (1,731 + 69) |
| `stf_documents` | 338 |
| `greens_parks` / `greens_species` | 638 / 1,815 |

### 7.3 How to query it
```sql
-- awards far below the estimate
select letter_date, estimated_rs, tendered_rs, ratio, tender_id from dda.award_values
where checks like '%ratio ok%' and ratio < 0.6 order by ratio limit 20;
-- site tender rows and their eprocure record
select t.nit, e.tender_value, e.bids_count, e.stage_group, l.match
from dda.tenders t join dda.tender_links l using (page_url, row_no) join dda.eprocure_tenders e using (tender_id) limit 20;
-- STF meetings by year
select extract(year from uploaded), kind, count(*) from dda.stf_documents group by 1, 2 order by 1;
-- parks far behind target
select park_id, completed_pct from dda.greens_parks where completed_pct < 25 order by completed_pct;
```

## 8. Verification
- Tests: 40 passed (`python -m pytest tests -q`, 7 Nov 2026), also without `psycopg2`.
- CI: `check` green on `main` and on `report-gsap` (7 Nov 2026 20:28 CET); `setup` and `watch` workflows green.
- scrape-check (7 Nov 2026): `portal` on `dda-stf` and `dda-greens`, `watch` on `dda-watch`: 0 FAIL each.
- Cross-checks: bucket HEAD check of all stored files (all present); 22 of 34 award estimates equal the eprocure value; the watch read all 117 listings without an error.
- **Not checked:** the 84 site tenders "not found on eprocure" (could be missing in the team's eprocure data); the content of scanned PDFs.

## 9. Known gaps and quality issues
| # | Issue | Size | Impact / what to do |
|---|---|--:|---|
| 1 | **Scanned PDFs, no text** (until OCR) | 10,565 + 614 large files | OCR decision ([10](#10-risks-and-open-decisions)) |
| 2 | Award letters without an awarded amount | 137 of 349 with text; 1,155 without text | OCR, then `extract_awards` |
| 3 | Broken document links (at the source) | 346 | listed in `dda.broken_links` |
| 4 | Site tenders not linked to eprocure | 107 of 1,837 | 84 not found, 20 no key, 3 ambiguous (`dda.tender_unlinked`) |
| 5 | Files never delivered (at the source) | 3 | recorded as unretrievable |
| 6 | Watch items not yet in the main projects | 9 files, 4 page links | monthly discovery + Setup folds them in |
| 7 | eprocure tenders with a future `published_at` (team data) | 67 | tell the eprocure family owner |

## 10. Risks and open decisions
- **Risks:** `analysis.build_db` alone drops the link and award tables; use `python -m analysis.refresh`. GitHub stops scheduled workflows after 60 days without repository activity: the watch then needs one manual run.
- **To decide (trideep):**
  1. OCR of about 10,500 scanned PDFs: recommended, starting with award letters (fills [9](#9-known-gaps-and-quality-issues) #2) and Authority agendas.
  2. Raise the privacy indicator (contractor bank documents) with DDA: recommended, counts only.
  3. Raise the DDA Greens data-quality indicator: recommended.

## 11. Next steps
**To do now**
1. Each Monday after the watch: `python -m analysis.refresh --html /tmp/dda-html --sync`.

**To decide**
2. The three decisions in [10](#10-risks-and-open-decisions).

**Later**
3. Monthly: `myproxy run python discover.py --resume --repair`, then Setup (folds new pages and files into the main projects).
4. Text of the STF minutes (335 files): decisions per meeting.
5. Check 20 of the 84 "not found" tenders by hand on eprocure.gov.in.

**Housekeeping**
6. Old helper `~/redispatch-dda-scrape.sh` removed. Release the box proxy when done: `myproxy release`.
