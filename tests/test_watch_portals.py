"""Change watch and the small portals: pure parts, no network."""
import portals
import watch


def test_new_links_ignore_known_and_pager():
    parsed = [{"page_links": ["http://dda.gov.in/tenders", "https://dda.gov.in/new-page", "https://dda.gov.in/tenders?page=3"],
               "documents": ["https://dda.gov.in/sites/default/files/tender/a b.pdf", "https://dda.gov.in/sites/default/files/tender/new.pdf"]}]
    pages, docs = watch.new_links(parsed, {"https://dda.gov.in/tenders"},
                                  {"https://dda.gov.in/sites/default/files/tender/a%20b.pdf"})
    assert pages == ["https://dda.gov.in/new-page"]
    assert docs == ["https://dda.gov.in/sites/default/files/tender/new.pdf"]


def test_known_scope_reads_seeds():
    pages, docs, listings = watch.known_scope()
    assert len(pages) > 1000 and len(docs) > 10000
    assert "https://dda.gov.in/archive-tender" in listings


def test_stf_page_files_and_rows():
    html = ('<title>STF</title><table><tr><td>1</td><td><a href="AgendaDoc/1-63rd%20Meeting.pdf">63rd</a></td></tr></table>'
            '<a href="Doc/ManualMobileApp.PDF">manual</a>')
    d = portals.stf_page(html, "https://stf.dda.org.in/STF-Meeting-Agenda-Title.aspx")
    assert d["files"] == ["https://stf.dda.org.in/AgendaDoc/1-63rd%20Meeting.pdf"]      # the app manual is left out
    assert d["rows"] == [["1", "63rd"]]


def test_greens_endpoints():
    e = portals.greens_endpoints([{"id": 7}])
    assert e[:2] == ["plantation/dashboard", "plantation/filter/parks"]
    assert "plantation/species-summary?parkId=7&speciesType=Shrub" in e and len(e) == 5
