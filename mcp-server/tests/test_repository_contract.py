import sqlite3

import pytest

from cleandrop_mcp.domain import DatabaseUnavailable, DeleteStatus
from cleandrop_mcp.repository import (
    SqliteDeletionCanceller,
    SqliteDownloadReader,
    _connect,
)


@pytest.fixture
def reader(db):
    return SqliteDownloadReader(db.path)


@pytest.fixture
def canceller(db):
    return SqliteDeletionCanceller(db.path)


def search(reader, **kw):
    args = dict(terms=[], status=None, since_days=None, limit=50)
    args.update(kw)
    return reader.search(**args)


def test_reads_rows_written_by_the_real_companion(db, reader):
    row_id = db.add("invoice.pdf", page_title="ACME Invoice")
    [d] = search(reader)
    assert (d.id, d.filename, d.page_title, d.status) == (
        row_id, "invoice.pdf", "ACME Invoice", "SCHEDULED",
    )
    assert d.size_bytes == 1234


def test_reader_connection_is_physically_read_only(db):
    db.add()
    with pytest.raises(DatabaseUnavailable):
        with _connect(db.path, read_only=True) as conn:
            conn.execute("UPDATE downloads SET delete_status='DELETED'")


def test_reader_works_while_writer_holds_an_open_transaction(db, reader):
    # This is what WAL buys: the scheduler can be mid-write and the MCP
    # server still reads a consistent snapshot without blocking.
    db.add("a.pdf")
    writer = sqlite3.connect(db.path)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE downloads SET page_title = 'uncommitted'")
    try:
        [d] = search(reader)
        assert d.page_title == "Quarterly Report"
    finally:
        writer.rollback()
        writer.close()


def test_incognito_downloads_are_invisible_everywhere(db, reader, canceller):
    hidden = db.add("secret.pdf", incognito=True)
    assert search(reader) == []
    assert reader.scheduled(within_days=None, limit=10) == []
    assert reader.get(hidden) is None
    assert canceller.cancel(hidden) is False


def test_search_matches_filename_title_and_host_case_insensitively(db, reader):
    db.add("invoice.pdf", page_title="Misc", url="https://billing.acme.io/x")
    db.add("photo.png", page_title="Holiday Photos", url="https://cdn.example.com/p")
    assert [d.filename for d in search(reader, terms=["INVOICE"])] == ["invoice.pdf"]
    assert [d.filename for d in search(reader, terms=["holiday"])] == ["photo.png"]
    assert [d.filename for d in search(reader, terms=["acme.io"])] == ["invoice.pdf"]


def test_all_terms_must_match(db, reader):
    db.add("tax_invoice.pdf")
    db.add("invoice.pdf")
    assert len(search(reader, terms=["invoice"])) == 2
    assert [d.filename for d in search(reader, terms=["invoice", "tax"])] == [
        "tax_invoice.pdf"
    ]


def test_like_wildcards_in_user_input_are_literal(db, reader):
    db.add("a.pdf")
    assert search(reader, terms=["%"]) == []
    assert search(reader, terms=["_"]) == []


def test_sql_injection_attempt_is_just_text(db, reader):
    db.add("a.pdf")
    assert search(reader, terms=["'; DROP TABLE downloads; --"]) == []
    assert len(search(reader)) == 1


def test_secret_in_url_query_string_is_not_searchable(db, reader):
    db.add("a.pdf", url="https://example.com/f.pdf?token=SECRET123")
    assert search(reader, terms=["SECRET123"]) == []


def test_status_filter_and_real_scheduler_transitions(db, reader):
    a = db.add("a.pdf", delete_after="2000-01-01T00:00:00.000Z")
    db.add("b.pdf")
    # Drive the row through the companion's own state machine.
    assert db.m.claim_download_for_deletion(a)
    db.m.update_delete_status(a, "DELETED")
    deleted = search(reader, status=DeleteStatus.DELETED)
    assert [d.filename for d in deleted] == ["a.pdf"]
    assert deleted[0].deleted_at is not None
    assert [d.filename for d in search(reader, status=DeleteStatus.SCHEDULED)] == ["b.pdf"]


def test_scheduled_orders_soonest_first_and_filters_by_window(db, reader):
    db.add("later.pdf", delete_after="2999-01-01T00:00:00.000Z")
    db.add("soon.pdf", delete_after="2000-01-02T00:00:00.000Z")
    names = [d.filename for d in reader.scheduled(within_days=None, limit=10)]
    assert names == ["soon.pdf", "later.pdf"]
    assert [d.filename for d in reader.scheduled(within_days=7, limit=10)] == ["soon.pdf"]


def test_cancel_only_succeeds_while_scheduled(db, reader, canceller):
    row = db.add()
    assert canceller.cancel(row) is True
    assert reader.get(row).status == "CANCELLED"
    assert canceller.cancel(row) is False  # idempotent, no error


def test_cancel_loses_cleanly_to_the_scheduler_claim(db, reader, canceller):
    row = db.add(delete_after="2000-01-01T00:00:00.000Z")
    assert db.m.claim_download_for_deletion(row)  # scheduler got there first
    assert canceller.cancel(row) is False
    assert reader.get(row).status == "DELETING"  # we did not clobber it


def test_cancelled_file_is_then_ignored_by_the_real_scheduler(db, canceller):
    row = db.add(delete_after="2000-01-01T00:00:00.000Z")
    assert canceller.cancel(row)
    assert db.m.get_expired_downloads() == []
    assert db.m.claim_download_for_deletion(row) is False


def test_missing_database_gives_a_helpful_error(tmp_path):
    with pytest.raises(DatabaseUnavailable, match="not found"):
        SqliteDownloadReader(tmp_path / "nope.db").get(1)
