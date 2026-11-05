# DDA scraper: scope and findings

**Subject:** the public website of the Delhi Development Authority, `https://dda.gov.in/`.
**Family:** `dda` (repo `s1d-labs/dda`). **Date:** 2026-11-04, updated 2026-11-05 (scrape complete).
**Status:** the scrape is complete. All 3,046 pages and 22,746 documents that the site delivers are stored. This report
gives the measured scope, the verification and the findings. The HTML version is `reports/dda-audit.html`.

This report uses ASD-STE100 Simplified Technical English. It names no private individuals.

---

## 1. Summary

- The site is a Drupal content site with a Hindi mirror under `/hi/`.
- The discovery crawl and the repair pass found **3,046 unique pages** and **23,095 unique documents**.
- The documents are mostly PDF files. The crawl also found map files (KMZ), spreadsheets, archives and application files.
- The scraper collects two kinds of record: one per page and one per document. It stores each document file in the bucket.
- The scrape runs on GitHub runners through the hub India proxy. The site answers only from India.
- No login, OTP or captcha system was accessed. The transactional portals are separate systems and stay out of scope.
- The organised tables are in the workspace database `ws_trideep`, schema `dda`. The HTML audit report gives the findings.

## 2. How the scraper reaches the site

The site has three access constraints. The scraper handles all three. See `ddatls.py`.

1. **India only.** The site answers only from Indian addresses. The pool uses `proxy="IN"`. Each worker uses one India proxy.
2. **Legacy TLS renegotiation.** OpenSSL 3.x refuses the handshake by default. The scraper enables `OP_LEGACY_SERVER_CONNECT`.
   This is a compatibility option. Certificate verification stays on.
3. **Incomplete certificate chain.** The server does not send its intermediate CA. The scraper ships the GlobalSign GCC R46
   OV intermediate and adds it to the trust store. The chain then verifies.

The scraper never disables certificate verification.

## 3. Measured scope

### 3.1 Pages

| Measure | Count |
|---|---|
| Unique pages found and scraped | 3,046 |
| English pages | 2,448 |
| Hindi pages (`/hi/`) | 598 |
| Internal page links that return HTTP 404 | 76 |

The numbers in 3.2 and 3.3 are from the first discovery (19,134 document URLs). The repair pass raised the unique
document scope to 23,095.

### 3.2 Documents by type

| Type | Count |
|---|---|
| PDF | 18,201 |
| KMZ (map boundary files) | 639 |
| DOC | 161 |
| DOCX | 59 |
| ZIP | 31 |
| APK (application files) | 12 |
| XLS / XLSX | 14 |
| Other (RAR, RTF, PPTX, EXE, TIF) | 15 |
| **Total documents** | **19,134** |

### 3.3 Top document sections (category)

The site stores documents under `/sites/default/files/<section>/`. The largest sections are:

| Section | Documents | Target data |
|---|---|---|
| `tender` | 2,411 | Tenders and corrigenda |
| `Personnel` | 1,819 | Staff orders and circulars |
| `pmuday` | 1,741 | Unauthorised colony and PM-UDAY lists and orders |
| `Landmgmt` | 997 | Land management |
| `Engineering` | 958 | Engineering |
| `public-notice` | 827 | Public notices |
| `LandDisposal` | 784 | Auctions and land disposal |
| `layoutplan` | 729 | Layout plans |
| `class-iv` / `class-v` | 1,366 | Recruitment and result documents |
| `horticulture_division` | 639 | Horticulture |
| `RTI` | 570 | Right to Information documents |
| `Accounts` | 529 | Finance and accounts |
| `technical_committee` | 410 | Technical committee |

## 4. Target data coverage

The request named five kinds of target data. The crawl found all five.

- **Unauthorised colony lists:** the page `/pm-uday/list-of-colonies-affluent-colonies` links the list of 1,731 unauthorised
  colonies (`1731_uc.pdf`) and the list of 69 affluent colonies. The `pmuday` section holds about 1,700 documents. The `RTI`
  and `gazette-notification` sections hold the regularisation gazette notifications.
- **Tenders:** the `/tenders` page links the external e-procurement portal. The `tender` section holds about 2,400 tender files.
- **Notices:** the `/public-notices` and `/whats-new` pages list notices. The `public-notice` and `notice` sections hold the files.
- **Public documents:** every file under `/sites/default/files/` is collected (about 16,000 files).
- **All other public pages and files:** the breadth-first crawl follows every internal link, so it reaches the whole site.

## 5. What the scraper collects

- **Page record:** URL, title, breadcrumb category, published dates, Drupal table rows (title, date, attachment links),
  internal links, external links. The raw page is stored in the bucket.
- **Document record:** URL, filename, type, size, SHA-256, content type, source page. The file is stored in the bucket.
- **Duplicates:** each record id is a hash of the URL. A re-run replaces the record, so there are no duplicates.

## 6. Security and access findings

This section records indicators, not findings of wrongdoing.

- **Weak TLS configuration (indicator).** The server requires legacy TLS renegotiation, which modern clients refuse by default.
  The server also sends an incomplete certificate chain. Both are signs of an old or incomplete TLS configuration.
- **No authentication bypass.** The scraper did not access any login, OTP or captcha system. It collected only public pages
  and public files.
- **Out-of-scope portals.** The transactional portals need a login and are separate systems. The scraper records them only as
  external links. These portals are:
  - `eservices.dda.org.in`, `online.dda.org.in`, `citzservices.dda.org.in`, `ddaservices.dda.org.in` (DDA e-services);
  - `ddalop.org.in` (land pooling);
  - `eprocure.gov.in` (central e-procurement).

## 7. Verification of the scrape

We checked the stored records against the site structure. The checks found these defects. We fixed all of them.

| Check | Result | Action |
|---|---|---|
| One spelling per URL | 221 pages were scraped two times (`http://` and `https://`). 27 documents had two spellings. | `crawl.canon_url` gives one spelling. |
| HTML entities in links | 157 document links were lost. The crawler read `&amp;` in a file name as text. | Links are unescaped. |
| Pager coverage | 395 listing pages were not reached. Example: 191 of 285 pages of the tender archive. | A `?page=N` link queues pages 1 to N. |
| Failed downloads | 346 documents return HTTP 404 on the site. | One broken-link record. No retries. |
| Large downloads | A dropped connection in a 40 MB file stopped a worker process. | Only the item fails. |
| Dates | Two-digit years became 20xx (1986 became 2086). | Two-digit years resolve to the past. |
| Discovery of files | A file linked as a page was read in full (more than 400 MB). | Discovery reads the headers first. |
| Files never delivered | The server cuts 2 files at the same point on every try. 1 link has no file name. The pool ran about 38 runner jobs an hour to retry these 3 files. | After 10 tries the file is recorded as unretrievable. |
| Bucket completeness | HEAD check of all 22,746 stored files. | All present. All sizes match. |
| Link to eprocure | The first key parser missed references that start with "NIT No." or "NIQ No.", and combined notices. | Fixed. 1,506 rows link. |

The repair pass (`discover.py --resume --repair`) added 397 pages and 3,988 documents. Setup added them to the queues.

## 8. Findings from the data

These are indicators, not findings of wrongdoing.

- **Unauthorised colonies.** We extracted the list of 1,731 colonies and the list of 69 affluent colonies (text PDF, no OCR).
  1,205 of the 1,731 colonies have a final boundary map on the site. 135 have the remark "can not be delineated as per SOP".
  154 are not in the boundary table. All final boundary maps have upload dates from March to August 2020.
- **Tenders on the site.** The site has 1,919 tender rows with 1,470 NIT numbers. 143 rows (7.5%) are "re-invited".
- **Awards are not on the central portal.** The team database has 53,170 DDA tenders from `eprocure.gov.in`. Only 1,070 (2.0%)
  reach the stage "awarded"; 45,894 (86.3%) stay "in evaluation". This is the lowest awarded share of the ten largest buyers
  on the portal. 243 of the 252 eprocure tenders that have an award letter on the DDA site still show "in evaluation" there. 14 letters print the eprocure Tender ID; all 14 are "in evaluation".
- **Link between site and portal.** 1,506 of 1,837 tender rows with an NIT number (82.0%) link to an eprocure tender
  (`link_eprocure.py`). Where eprocure shows an award, the median award is 0.74 times the estimated value.
- **Single bids.** On eprocure, 2.5% to 9.3% of DDA tenders with bids have exactly one bid, by year. Some divisions are
  above 15% since 2022.
- **Text in documents.** 10,524 of 21,089 stored PDF files (49.9%) have a text layer; the rest are scans that need OCR. The text is in `dda.document_text` with a full-text index.
- **Debarments.** The site has 39 debarment or suspension orders and 3 withdrawals.
- **Broken links.** 346 document links return HTTP 404. Most are in the contractor enlistment folders (`class-i` to `class-v`).
- **Duplicate files.** 1,252 files occur at more than one URL (1,494 extra copies, 2.4 GB).
- **Privacy indicator.** The archive of registered contractors links 2,171 files. They include about 540 bank solvency
  certificates and 540 application forms. These can hold personal and financial data. We did not open these files. Also, 73 of 349 award letters with a text layer print a bank account number of the contractor (counted only).
- **Security indicators.** Legacy TLS renegotiation, an incomplete certificate chain, links to raw IP addresses over plain
  HTTP, one link to a vendor staging host, and two links to DDA services that return HTTP 404.

## 9. Failures and missing data

- **Broken links on the site:** 346 documents and 76 pages return HTTP 404.
- **Files the server does not deliver:** 3 documents. The server cuts one 40 MB PDF at the same byte on every try, cuts
  one XLS before the first byte, and refuses a link with no file name (`/.pdf`). After 10 tries the scraper records
  them as unretrievable.
- **Bucket check:** all 22,746 stored documents are in the bucket with the same size as the record (HEAD check).
- **Reliability:** the hub had one short outage during the run. The workers failed and then restarted by themselves.

## 10. How to run it

1. **Discover the site** (writes `seeds.json`): `myproxy run python discover.py`
2. **Repair the scope** after timeouts: `myproxy run python discover.py --resume --repair`
3. **Apply to the hub** (registers the projects and seeds the queue): run the Setup workflow (Actions, then setup).
4. **Scrape**: the hub starts the `scrape-runner` workflow of pool members for family `dda` by itself.
5. **Organised tables**: `python build_db.py --html DIR` and `python extract_colonies.py ...` (see README).
6. **Report**: `python analyze.py`, then `python report_html.py analysis.json report.html`. `python report.py` gives the coverage JSON.

## 11. Current progress

- **Pages:** 3,046 of 3,046 scraped (100%).
- **Documents:** 22,746 stored (about 87 GB), 346 broken links, 3 not delivered by the server. Total 23,095.
- **Organised data:** workspace database `ws_trideep`, schema `dda` (see README).
- **Full text:** `dda.document_text` holds 21,089 PDFs (all stored PDFs up to 25 MB); 10,524 have text.
