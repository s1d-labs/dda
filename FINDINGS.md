# DDA scraper: scope and findings

**Subject:** the public website of the Delhi Development Authority, `https://dda.gov.in/`.
**Family:** `dda` (repo `s1d-labs/dda`). **Date:** 2026-11-04.
**Status:** the scraper is built, tested and live. The pool downloads the documents now. This report gives the measured
scope and the findings. The numbers are live and increase while the scrape runs.

This report uses ASD-STE100 Simplified Technical English. It names no private individuals.

---

## 1. Summary

- The site is a Drupal content site with a full Hindi mirror under `/hi/`.
- The discovery crawl mapped the whole site and found **2,871 pages** and **19,134 documents** (28 pages stay unreached).
- The documents are mostly PDF files. The crawl also found map files, spreadsheets, archives and a few application files.
- The scraper collects two kinds of record: one per page and one per document. It stores each document file in the bucket.
- The scrape runs on GitHub runners through the hub India proxy. The site answers only from India.
- No login, OTP or captcha system was accessed. The transactional portals are separate systems and stay out of scope.

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
| Pages found | 2,871 |
| English pages | 2,191 |
| Hindi pages (`/hi/`) | 680 |
| Pages unreached (budget tail) | 28 |

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
- **Tenders:** the `/tenders` page links the external e-procurement portal. The `tender` section holds about 1,180 tender files.
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

## 7. Failures and missing data

- **Discovery errors:** 232 page fetches failed during discovery. The cause is a request timeout under proxy load.
  These pages can be fetched again with a resume crawl.
- **Download failures:** a small number of documents fail to download on the first try. The hub retries them automatically.
- **Pager depth limit:** the first discovery pass stopped at a page budget. A resume pass continued and drained the rest.
- **Reliability:** the hub had one short outage during the run. The workers failed and then restarted by themselves.

## 8. How to run it

1. **Discover the site** (writes `seeds.json`): `myproxy run python discover.py`
2. **Apply to the hub** (registers the projects and seeds the queue): run the Setup workflow (Actions → setup).
3. **Scrape on GitHub** (uses GitHub runners through the India proxy): run the `scrape-runner` workflow with `family=dda`.
4. **Report** (reads the hub database): `python report.py` → `report.json`.

## 9. Current progress

The scrape of about 16,000 documents is a multi-hour job. It continues on the pool after this report.
Run `python report.py` for the live numbers, or run `/report` for the team-format progress report.
