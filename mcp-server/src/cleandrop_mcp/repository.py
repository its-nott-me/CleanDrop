"""SQLite adapters for the ports in `domain`.

Two classes, two connection modes (Interface Segregation):
  * SqliteDownloadReader   -> opened `mode=ro`; physically cannot write.
  * SqliteDeletionCanceller -> read/write, but only exposes one guarded UPDATE.

A fresh connection is opened per call. SQLite connections are cheap, this
avoids cross-thread errors (the SDK may run sync tools on worker threads),
and every call sees a fresh WAL snapshot instead of a stale one.
"""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from .domain import (
    DatabaseUnavailable,
    DeleteStatus,
    Download,
    source_host,
)

_COLUMNS = (
    "id, original_filename, current_path, file_size, mime_type, url, "
    "page_title, delete_status, delete_after, deleted_at, created_at"
)

# Incognito downloads are excluded from every query. The user chose
# private browsing; an AI assistant should not be able to surface them.
_VISIBLE = "incognito = 0"

# If the background scheduler is mid-write, wait instead of failing.
_BUSY_TIMEOUT_MS = 5000


def _escape_like(term: str) -> str:
    return (
        term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


@contextmanager
def _connect(db_path: Path, *, read_only: bool) -> Iterator[sqlite3.Connection]:
    if not db_path.exists():
        raise DatabaseUnavailable(
            f"CleanDrop database not found at {db_path}. CleanDrop creates it "
            "the first time it runs; has it been installed and used yet?"
        )
    target = db_path.as_uri() + ("?mode=ro" if read_only else "")
    try:
        conn = sqlite3.connect(target, uri=True)
    except sqlite3.OperationalError as exc:
        raise DatabaseUnavailable(f"Cannot open CleanDrop database: {exc}") from exc

    with closing(conn):
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        # Lets SQL match on hostname without exposing full URLs.
        conn.create_function("url_host", 1, source_host, deterministic=True)
        try:
            yield conn
        except sqlite3.OperationalError as exc:
            raise DatabaseUnavailable(f"CleanDrop database error: {exc}") from exc


def _to_download(row: sqlite3.Row) -> Download:
    return Download(
        id=row["id"],
        filename=row["original_filename"],
        path=row["current_path"],
        size_bytes=row["file_size"],
        mime_type=row["mime_type"],
        url=row["url"],
        page_title=row["page_title"],
        status=row["delete_status"],
        delete_after=row["delete_after"],
        deleted_at=row["deleted_at"],
        created_at=row["created_at"],
    )


class SqliteDownloadReader:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def search(
        self,
        *,
        terms: Sequence[str],
        status: DeleteStatus | None,
        since_days: int | None,
        limit: int,
    ) -> list[Download]:
        clauses = [_VISIBLE]
        params: list[object] = []

        # Every term must match somewhere (AND), so "tax invoice" narrows
        # results rather than widening them.
        for term in terms:
            like = f"%{_escape_like(term)}%"
            clauses.append(
                "(original_filename LIKE ? ESCAPE '\\' "
                "OR page_title LIKE ? ESCAPE '\\' "
                "OR url_host(url) LIKE ? ESCAPE '\\')"
            )
            params += [like, like, like]

        if status is not None:
            clauses.append("delete_status = ?")
            params.append(status.value)

        if since_days is not None:
            clauses.append("datetime(created_at) >= datetime('now', ?)")
            params.append(f"-{int(since_days)} days")

        sql = (
            f"SELECT {_COLUMNS} FROM downloads WHERE {' AND '.join(clauses)} "
            "ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        params.append(limit)

        with _connect(self._db_path, read_only=True) as conn:
            return [_to_download(r) for r in conn.execute(sql, params)]

    def scheduled(
        self, *, within_days: int | None, limit: int
    ) -> list[Download]:
        clauses = [_VISIBLE, "delete_status = 'SCHEDULED'"]
        params: list[object] = []

        if within_days is not None:
            clauses.append("datetime(delete_after) <= datetime('now', ?)")
            params.append(f"+{int(within_days)} days")

        sql = (
            f"SELECT {_COLUMNS} FROM downloads WHERE {' AND '.join(clauses)} "
            "ORDER BY datetime(delete_after) ASC, id ASC LIMIT ?"
        )
        params.append(limit)

        with _connect(self._db_path, read_only=True) as conn:
            return [_to_download(r) for r in conn.execute(sql, params)]

    def get(self, download_id: int) -> Download | None:
        sql = f"SELECT {_COLUMNS} FROM downloads WHERE id = ? AND {_VISIBLE}"
        with _connect(self._db_path, read_only=True) as conn:
            row = conn.execute(sql, (download_id,)).fetchone()
        return _to_download(row) if row else None


class SqliteDeletionCanceller:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def cancel(self, download_id: int) -> bool:
        # The `AND delete_status = 'SCHEDULED'` guard is the same
        # compare-and-set the scheduler uses to claim a row for deletion
        # (claim_download_for_deletion). Whichever side commits first
        # wins; the loser changes zero rows. That makes this safe to run
        # concurrently with the scheduler without any extra locking.
        sql = (
            "UPDATE downloads SET delete_status = 'CANCELLED', "
            "updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ? AND delete_status = 'SCHEDULED' AND {_VISIBLE}"
        )
        with _connect(self._db_path, read_only=False) as conn:
            cursor = conn.execute(sql, (download_id,))
            conn.commit()
            return cursor.rowcount > 0
