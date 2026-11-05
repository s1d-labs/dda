"""Download handling with a fake hub and a fake session: no network."""
import requests

import crawl


class FakeHub:
    def __init__(self):
        self.records, self.completed, self.failures, self.metrics, self.uploads = {}, [], [], {}, []

    def metric(self, name, value=1):
        self.metrics[name] = self.metrics.get(name, 0) + value

    def error(self):
        self.metric("_error")

    def block(self):
        self.metric("_block")

    def record(self, rid, data):
        self.records[rid] = data

    def complete(self, keys, status, error=None, fetched=0):
        self.completed.append((keys[0], status, error, fetched))

    def failure(self, kind, key, reason, **detail):
        self.failures.append((kind, key, reason))

    def upload_many(self, files):
        self.uploads.extend(files)


class FakeResponse:
    def __init__(self, status, body=b"", broken=False, ctype="application/pdf"):
        self.status_code, self._body, self._broken = status, body, broken
        self.headers = {"Content-Type": ctype}
        self.url, self.encoding = "https://dda.gov.in/x", "utf-8"

    @property
    def content(self):
        if self._broken:
            raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead")
        return self._body

    @property
    def text(self):
        return self._body.decode()

    def close(self):
        pass


class FakeSession:
    def __init__(self, resp):
        self.resp = resp

    def get(self, *a, **k):
        return self.resp

    head = get


def _item(url="https://dda.gov.in/sites/default/files/tender/a.pdf", kind="doc"):
    return {"key": "d-1", "payload": {"url": url, "type": kind}}


def test_doc_ok_is_stored_and_uploaded():
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(200, b"%PDF-1.4 x")), _item())
    assert hub.completed == [("d-1", "done", None, 1)]
    (rec,) = hub.records.values()
    assert rec["bytes"] == 10 and rec["ext"] == "pdf"
    assert hub.uploads and hub.uploads[0][0] == "docs/sites/default/files/tender/a.pdf"


def test_dropped_connection_mid_file_fails_the_item_not_the_worker():
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(200, broken=True)), _item())   # must not raise
    assert hub.completed[0][1] == "failed"
    assert hub.metrics.get("http_error") == 1
    assert not hub.records


def test_404_document_is_a_broken_link_and_not_retried():
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(404, ctype="text/html")), _item())
    assert hub.completed == [("d-1", "done", None, 0)]
    (rec,) = hub.records.values()
    assert rec["broken"] is True and rec["status"] == 404
    assert hub.failures[0][0] == "broken-link"
    assert hub.metrics.get("http_404") == 1


def test_500_document_fails_for_retry():
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(500)), _item())
    assert hub.completed[0][1] == "failed" and "HTTP 500" in hub.completed[0][2]


def test_404_page_is_a_broken_link():
    hub = FakeHub()
    crawl.do_page(hub, FakeSession(FakeResponse(404, ctype="text/html")),
                  _item("https://dda.gov.in/old-page", "page"))
    assert hub.completed == [("d-1", "done", None, 0)]


def test_kmz_is_a_document():
    assert crawl.classify("https://dda.gov.in/sites/default/files/layout/x.kmz") == "document"


def test_cut_transfer_retries_then_gives_up():
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(200, broken=True)), dict(_item(), attempts=2))
    assert hub.completed[0][1] == "failed" and "cut" in hub.completed[0][2]
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(200, broken=True)), dict(_item(), attempts=crawl.GIVE_UP_AFTER))
    assert hub.completed == [("d-1", "done", None, 0)]
    (rec,) = hub.records.values()
    assert rec["unretrievable"] is True


def test_403_document_gives_up_after_many_attempts():
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(403, ctype="text/html")), dict(_item(), attempts=1))
    assert hub.completed[0][1] == "failed" and hub.metrics.get("_block") == 1
    hub = FakeHub()
    crawl.do_doc(hub, FakeSession(FakeResponse(403, ctype="text/html")), dict(_item(), attempts=12))
    assert hub.completed[0][1] == "done"
