# dda: Delhi Development Authority scraper

Scraper family of the s1d-labs scrape pool for the public website of the Delhi Development Authority
(`https://dda.gov.in/`) and two small public DDA portals. It collects every public page and file: tenders, notices,
orders, circulars, unauthorised colony and PM-UDAY material, land records, and all other public pages.

| | |
|---|---|
| **Status** | Complete. 3,046 pages and 22,755 documents (86 GB) are stored. A weekly watch adds new items. |
| **Report** | [`reports/dda-audit.html`](reports/dda-audit.html): open it in a browser; it works offline. |
| **Progress report** | [`REPORT.md`](REPORT.md) (team format) · scope and findings: [`FINDINGS.md`](FINDINGS.md) |
| **Data** | Workspace database `ws_trideep`, schema `dda` (Metabase "Workspace: trideep") · bucket `dda-*/` |
| **Pool reference** | [`CLAUDE.md`](CLAUDE.md): `scrape.json`, runner env vars, `scrape_hub_client`, metrics |

## Projects

| Project | Task | Source | Network | Queue item |
|---|---|---|---|---|
| `dda-pages` | `crawl` | dda.gov.in HTML pages | India proxy | one page |
| `dda-docs` | `crawl` | dda.gov.in files (PDF, DOC, XLS, KMZ, ...) | India proxy | one file |
| `dda-watch` | `watch` | first page of every listing, new pages and files | India proxy | one week |
| `dda-stf` | `portal` | stf.dda.org.in: agendas, minutes, notices | none | one page or file |
| `dda-greens` | `portal` | ddagreens.dda.org.in: plantation JSON API | none | one API call |

Out of scope (login, OTP or captcha): `eservices.dda.org.in`, `online.dda.org.in`, `citzservices.dda.org.in`,
`drms.dda.org.in`, `vipreferences.dda.org.in`, `ddalop.org.in`. They appear only as external links. The STF login,
complaint forms and officer lists, and the Greens officer pages are left out because they can hold personal data.

## How access works

1. **India only.** dda.gov.in answers only from Indian IP addresses. The pool uses `proxy="IN"`; on the box use
   `myproxy run ...`. The STF and Greens portals answer from anywhere.
2. **Legacy TLS renegotiation.** OpenSSL 3 refuses the handshake by default. `ddatls.py` enables
   `OP_LEGACY_SERVER_CONNECT`, a compatibility option only.
3. **Incomplete certificate chain.** The server does not send its intermediate CA. `certs/` holds the GlobalSign
   GCC R46 OV intermediate. Certificate verification stays **on**; the scraper never disables it.

## Repository layout

```
crawl.py          task 'crawl': page parse (Drupal views, HTML tables) and file download
watch.py          task 'watch': weekly check of all listings, stores new pages and files
portals.py        task 'portal': STF pages and files, Greens API calls; 'discover' mode on the box
discover.py       breadth-first discovery of dda.gov.in -> seeds.json (--resume --repair)
ddatls.py         requests session for the legacy TLS and the missing intermediate
family.py         the five projects and their queue items     setup_family.py   applies them to the hub
seed_watch.py     puts this week's watch item in the queue     scrape.json       family, setup, tasks
seeds.json        discovered scope (pages, documents)          certs/            GlobalSign intermediate
analysis/         box-only analysis (python -m analysis.<step>), GSAP files in analysis/vendor/
data/             small data sets: colony list CSV, portal seeds, link check, PDF census
reports/          dda-audit.html (the report); generated JSON is not committed
tests/            offline tests (parsing, downloads, discovery, links, awards, watch, portals)
.github/workflows check (tests on every push), setup (apply family.py), watch (every Monday 02:30 UTC)
```

## Run it

| Step | Command |
|---|---|
| Discover the site | `myproxy run python discover.py` (then `--resume --repair` after timeouts) |
| Discover the portals | `python portals.py discover` |
| Try one page or file | `myproxy run python crawl.py --local https://dda.gov.in/whats-new` |
| Try the watch | `myproxy run python watch.py --local` (lists what is new, stores nothing) |
| Check a task | `myproxy run scrape-check --project dda-pages --items 2` (needs `scrape-hub-client` 0.10 or later; `pip install -r analysis/requirements.txt` installs it) |
| Apply to the hub | Actions -> **setup** -> Run workflow (inputs: `docs_pool`, `reset_failed`) |
| Weekly watch | runs by itself; Actions -> **watch** -> Run workflow to run it now |
| Tests | `python -m pytest tests -q` |

The hub starts the pool runners by itself when a project has work.

## Analysis (box only)

```
pip install -r analysis/requirements.txt
eval "$(mybucket env)"                                   # read-only bucket key
python -m analysis.refresh --html /tmp/dda-html --sync   # tables, links, award values, figures, report
```

| Step | What it makes |
|---|---|
| `analysis.build_db` | schema `dda`: pages, documents, listing rows, HTML tables, tenders, awards, debarments, land awards, colonies, STF, Greens |
| `analysis.link_eprocure` | links site tenders and award letters to DDA's 53,170 eprocure tenders (`tender_links`, `award_links`, `tender_unlinked`) |
| `analysis.extract_awards` | estimated cost and awarded amount from the award letters (`award_values`) |
| `analysis.extract_colonies` | the PM-UDAY colony lists from the text PDFs (`unauthorised_colonies`, `data/unauthorised_colonies.csv`) |
| `analysis.extract_text` | text layer of the stored PDFs, no OCR (`document_text`, full-text index); time-bounded and resumable |
| `analysis.pdf_census` | share of PDFs with a text layer (`data/pdf_census.json`) |
| `analysis.linkcheck` | HEAD check of failed downloads (`data/linkcheck.json`) |
| `analysis.analyze` + `analysis.report_html` | figures (`reports/analysis.json`) and the HTML report |
| `analysis.coverage` | discovery scope against the hub (`reports/coverage.json`) |
| `analysis.fold_watch` | adds what the weekly watch stored to `data/watch_known.json`, so the watch does not download it again; commit the file |

## Rules

- Public data only. No login, OTP or captcha system is accessed.
- Pool files go through the hub (`hub.upload_many`); no storage keys in this repository.
- Reports use ASD-STE100 Simplified Technical English and name no private individuals. Personal data (bank
  accounts, names) is counted, never copied into a report.
