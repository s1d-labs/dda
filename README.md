# dda — Delhi Development Authority scraper

This family scrapes the public website of the Delhi Development Authority (DDA), `https://dda.gov.in/`.
It collects every public page and every linked document (tenders, notices, public documents, policy pages,
unauthorised colony and PM-UDAY material, and all other public pages and files).

It is part of the s1d-labs scrape pool. The full technical contract is in `CLAUDE.md`.

## What it collects

- **Pages** (`dda-pages`): one record per public HTML page. Each record has the URL, title, breadcrumb
  category, published dates, Drupal view rows (title, date, attachment links), and classified links.
- **Documents** (`dda-docs`): one record per linked file (PDF, DOC, XLS, PPT, ZIP, ...). Each record has
  the URL, filename, type, size, SHA-256, and content type. The file itself goes to the family bucket.

The transactional e-services portals (`eservices.dda.org.in`, `online.dda.org.in`, `citzservices.dda.org.in`,
`ddalop.org.in`, and `eprocure.gov.in`) are separate systems that need a login. They are out of scope. The
scraper records them only as external links.

## How access works

DDA has three access constraints. The scraper handles all three:

1. **India only.** The site answers only from Indian IP addresses. Pool work uses `proxy="IN"`, so each
   worker runs through one of the hub's India proxies. From the box, use `myproxy run ...`.
2. **Legacy TLS renegotiation.** OpenSSL 3.x refuses the handshake by default. `ddatls.py` enables
   `OP_LEGACY_SERVER_CONNECT`. This is a compatibility option only.
3. **Incomplete certificate chain.** The server does not send its intermediate CA. `ddatls.py` ships the
   GlobalSign GCC R46 OV intermediate in `certs/` and adds it to the trust store. Certificate verification
   stays **on**. The scraper never disables verification.

## Run it

1. **Discover the site** (enumerate pages and documents, write `seeds.json`):

   ```
   myproxy run python discover.py
   ```

2. **Test one page or document** without the hub:

   ```
   myproxy run python crawl.py --local https://dda.gov.in/whats-new
   myproxy run python crawl.py --local https://dda.gov.in/sites/default/files/2025-07/pio_list_2025.pdf
   ```

3. **Check the family** against the stand-in hub (through the proxy, because the site is India only):

   ```
   myproxy run scrape-check --project dda-pages --items 2
   ```

4. **Apply to the hub**: run the **setup** workflow (Actions → setup → Run workflow). It registers the
   projects, seeds the queue from `seeds.json`, and registers the health check. The pool then scrapes.

## Files

| File | What |
|---|---|
| `ddatls.py` | legacy-TLS requests session (verification stays on) |
| `discover.py` | breadth-first site crawl → `seeds.json` + scope summary |
| `crawl.py` | the `crawl` task: page parsing and document download |
| `family.py` | the two projects and their queue items (from `seeds.json`) |
| `setup_family.py` | registers projects, pool entries, health checks, seeds queues |
| `report.py` | reads the scraped data from the hub database and writes a coverage report |
| `certs/` | the GlobalSign intermediate CA the site fails to send |
| `tests/` | offline parse tests on a saved page |

## Rules

- Public data only. No login, OTP, or captcha systems are accessed.
- Files go through the hub (`hub.upload_many`); no storage keys in this repo.
- Reports use ASD-STE100 Simplified Technical English and name no private individuals.
