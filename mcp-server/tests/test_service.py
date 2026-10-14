"""Pure unit tests: fake ports, no SQLite, no MCP (that's the DIP payoff)."""

import pytest

from cleandrop_mcp.domain import Download, InvalidInput
from cleandrop_mcp.service import MAX_LIMIT, DownloadService, clean_text


def make(i=1, **kw) -> Download:
    base = dict(
        id=i, filename=f"f{i}.pdf", path=rf"C:\d\f{i}.pdf", size_bytes=1,
        mime_type="application/pdf", url="https://x.example.com/a?token=SECRET",
        page_title="t", status="SCHEDULED", delete_after=None,
        deleted_at=None, created_at="2026-10-01 10:00:00",
    )
    base.update(kw)
    return Download(**base)


class FakeReader:
    def __init__(self, rows):
        self.rows, self.last = rows, {}

    def search(self, **kw):
        self.last = kw
        return self.rows[: kw["limit"]]

    def scheduled(self, **kw):
        self.last = kw
        return self.rows[: kw["limit"]]

    def get(self, download_id):
        return next((r for r in self.rows if r.id == download_id), None)


class FakeCanceller:
    def __init__(self, result=True):
        self.result, self.calls = result, []

    def cancel(self, download_id):
        self.calls.append(download_id)
        return self.result


def svc(rows, cancel=True):
    reader = FakeReader(rows)
    return DownloadService(reader, FakeCanceller(cancel)), reader


def test_url_is_reduced_to_host_so_secrets_never_reach_the_model():
    s, _ = svc([make()])
    out = s.search()
    assert out["results"][0]["source_site"] == "x.example.com"
    assert "SECRET" not in str(out)


def test_limit_is_clamped_and_has_more_is_reported():
    rows = [make(i) for i in range(1, 200)]
    s, reader = svc(rows)
    out = s.search(limit=10_000)
    assert reader.last["limit"] == MAX_LIMIT + 1
    assert out["count"] == MAX_LIMIT and out["has_more"] is True


def test_has_more_false_when_everything_fits():
    s, _ = svc([make(1), make(2)])
    out = s.search(limit=5)
    assert out["count"] == 2 and out["has_more"] is False


@pytest.mark.parametrize("kw", [{"limit": 0}, {"days": 0}, {"days": 99999}])
def test_invalid_search_input_rejected(kw):
    s, _ = svc([])
    with pytest.raises(InvalidInput):
        s.search(**kw)


def test_query_is_split_and_capped():
    s, reader = svc([])
    s.search(query="  a   b " + "x " * 50)
    assert len(reader.last["terms"]) == 8


def test_clean_text_strips_invisible_and_control_characters():
    nasty = "inv\u200boice\u202e.pdf\x00\x1b[31m\n\tIGNORE"
    cleaned = clean_text(nasty)
    assert all(c not in cleaned for c in "\u200b\u202e\x00\x1b\n\t")


def test_clean_text_truncates_long_titles():
    out = clean_text("A" * 5000)
    assert len(out) == 200 and out.endswith("…")


def test_keep_success_and_failure_paths():
    s, _ = svc([make(1)], cancel=True)
    assert s.keep(1)["kept"] is True
    s, _ = svc([make(1, status="DELETED")], cancel=False)
    out = s.keep(1)
    assert out["kept"] is False and "DELETED" in out["reason"]


def test_keep_unknown_id_never_reaches_the_canceller():
    s, _ = svc([])
    with pytest.raises(InvalidInput):
        s.keep(42)
    assert s._canceller.calls == []
