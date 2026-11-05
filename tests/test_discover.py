"""Discovery link handling: no network."""
import crawl
import discover


def test_amp_in_href_is_unescaped():
    html = '<a href="/sites/default/files/horticulture_division/L%20&amp;%20T%20Park.kmz">x</a>'
    (link,) = list(discover.links_on(html, "https://dda.gov.in/horticulture"))
    assert "&amp;" not in link and link.endswith("/L%20&%20T%20Park.kmz")
    assert discover.classify(link)[0] == "document"
    d = crawl.parse(html, "https://dda.gov.in/horticulture")
    assert d["documents"] == [link]


def test_semicolon_stays_in_path():
    assert crawl.canon_url("https://dda.gov.in/a;b.pdf") == "https://dda.gov.in/a;b.pdf"


def test_pager_link_queues_every_page():
    assert discover.pager_pages("https://dda.gov.in/archive-tender?page=3") == [
        "https://dda.gov.in/archive-tender?page=1", "https://dda.gov.in/archive-tender?page=2",
        "https://dda.gov.in/archive-tender?page=3"]
    assert discover.pager_pages("https://dda.gov.in/tenders") == []


def test_repair_targets():
    prev = {"pages": ["https://dda.gov.in/archive-tender", "https://dda.gov.in/archive-tender?page=1",
                      "https://dda.gov.in/archive-tender?page=4"],
            "errors": {"https://dda.gov.in/sites/default/files/x/L%20&amp;%20T.pdf": "HTTP 404"}}
    refetch, gaps, fixed = discover.repair_targets(prev)
    assert refetch == ["https://dda.gov.in/archive-tender"]
    assert gaps == ["https://dda.gov.in/archive-tender?page=2", "https://dda.gov.in/archive-tender?page=3"]
    assert list(fixed.values()) == ["https://dda.gov.in/sites/default/files/x/L%20&%20T.pdf"]
