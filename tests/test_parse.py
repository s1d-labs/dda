"""Parsing tests on saved dda.gov.in pages: fast, no network."""
from pathlib import Path

import crawl

PAGES = Path(__file__).parent / "pages"


def _whatsnew():
    return crawl.parse((PAGES / "whats-new.html").read_text(encoding="utf-8"),
                       "https://dda.gov.in/whats-new")


def test_page_metadata():
    d = _whatsnew()
    assert d["type"] == "page"
    assert d["title"] == "What's New"
    assert d["category"]                                   # non-empty
    assert d["url"] == "https://dda.gov.in/whats-new"


def test_listing_rows_have_titles_and_dates():
    d = _whatsnew()
    assert len(d["rows"]) >= 5
    # the header row is dropped: every row has real text, not the column labels
    assert all("Publishing Date" not in r["text"] for r in d["rows"])
    dated = [r for r in d["rows"] if r["date"] and r["date"][:2] == "20"]
    assert dated, "at least one row has an ISO date"


def test_documents_are_absolute_and_deduped():
    d = _whatsnew()
    assert d["n_documents"] >= 1
    assert d["documents"] == sorted(set(d["documents"]))   # no duplicates
    assert all(u.startswith("https://dda.gov.in/") for u in d["documents"])
    assert all(crawl.classify(u) == "document" for u in d["documents"])


def test_links_split_internal_external():
    d = _whatsnew()
    assert all(crawl.classify(u) == "page" for u in d["page_links"])
    assert all(crawl.classify(u) == "external" for u in d["external_links"])


def test_record_id_stable_and_short():
    a = crawl.record_id("https://dda.gov.in/whats-new")
    b = crawl.record_id("https://dda.gov.in/whats-new#x")   # fragment ignored
    assert a == b and 0 < len(a) <= 20


def test_bucket_path_is_safe():
    p = crawl.bucket_path("https://dda.gov.in/sites/default/files/2025-07/a b.pdf", "docs")
    assert p == "docs/sites/default/files/2025-07/a_b.pdf"
    assert ".." not in p


def test_iso_date():
    assert crawl.iso_date("04-11-2026") == "2026-11-04"
    assert crawl.iso_date("03.11.2026") == "2026-11-03"
    assert crawl.iso_date("no date here") is None


def test_empty_page():
    d = crawl.parse("<html><body>nothing</body></html>", "https://dda.gov.in/x")
    assert d["rows"] == [] and d["n_documents"] == 0


def test_iso_date_formats():
    assert crawl.iso_date("NIT 25-06-2026 Size") == "2026-06-25"
    assert crawl.iso_date("1965 24.04.1965 Size:57 MB") == "1965-04-24"
    assert crawl.iso_date("Stilt Parking Plan. 20-January-2021 Size") == "2021-01-20"
    assert crawl.iso_date("order dated 12/03/86") == "1986-03-12"      # not 2086
    assert crawl.iso_date("dated 01-02-24") == "2024-02-01"
    assert crawl.iso_date("Award No-1333 DHAKKA") is None
    assert crawl.iso_date("ref 12-11-0021") is None                     # not a real year


def test_date_with_space():
    assert crawl.iso_date("Tender document of CNG sites 31-12- 2025 Size :19.5 MB") == "2025-12-31"
