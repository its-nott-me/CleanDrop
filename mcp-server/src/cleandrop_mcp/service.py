"""Use-case layer. Knows nothing about SQLite or MCP.

Responsibilities (and only these): validate input, clamp limits, call the
ports, and shape results into what a model should see (sanitised, minimal).
"""

import unicodedata
from typing import Any

from .domain import (
    DeleteStatus,
    DeletionCanceller,
    Download,
    DownloadReader,
    InvalidInput,
    source_host,
)

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_TEXT = 200
MAX_TERMS = 8
MAX_TERM_LEN = 64
MAX_DAYS = 3650


def clean_text(value: str | None, max_len: int = MAX_TEXT) -> str | None:
    """Make website-controlled text safer to hand to a model.

    Filenames and page titles are written by whoever runs the site, so
    they are untrusted input that ends up in the model's context. This
    strips control and invisible formatting characters (zero-width,
    bidi overrides) and caps length. It reduces the prompt-injection
    surface; it does not eliminate it.
    """
    if value is None:
        return None
    kept = "".join(
        " " if ch.isspace() else ch
        for ch in value
        if not unicodedata.category(ch).startswith("C") or ch.isspace()
    )
    kept = " ".join(kept.split())
    if len(kept) > max_len:
        kept = kept[: max_len - 1] + "…"
    return kept


def _bounded(name: str, value: int | None, low: int, high: int) -> int | None:
    if value is None:
        return None
    if not low <= value <= high:
        raise InvalidInput(f"{name} must be between {low} and {high}.")
    return value


def _limit(limit: int) -> int:
    if limit < 1:
        raise InvalidInput("limit must be at least 1.")
    return min(limit, MAX_LIMIT)


def _view(d: Download) -> dict[str, Any]:
    return {
        "id": d.id,
        "filename": clean_text(d.filename),
        "path": clean_text(d.path, 300),
        "size_bytes": d.size_bytes,
        "mime_type": clean_text(d.mime_type, 100),
        "source_site": source_host(d.url),
        "page_title": clean_text(d.page_title),
        "status": d.status,
        "delete_after": d.delete_after,
        "deleted_at": d.deleted_at,
        "tracked_since": d.created_at,
    }


def _page(rows: list[Download], limit: int) -> dict[str, Any]:
    # Readers are asked for limit+1 rows so we can say honestly whether
    # more exist, instead of silently hiding results from the model.
    has_more = len(rows) > limit
    return {
        "count": min(len(rows), limit),
        "has_more": has_more,
        "results": [_view(r) for r in rows[:limit]],
    }


class DownloadService:
    def __init__(self, reader: DownloadReader, canceller: DeletionCanceller) -> None:
        self._reader = reader
        self._canceller = canceller

    def search(
        self,
        query: str = "",
        status: DeleteStatus | None = None,
        days: int | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        limit = _limit(limit)
        days = _bounded("days", days, 1, MAX_DAYS)
        terms = [t[:MAX_TERM_LEN] for t in query.split()][:MAX_TERMS]
        rows = self._reader.search(
            terms=terms, status=status, since_days=days, limit=limit + 1
        )
        return _page(rows, limit)

    def list_scheduled(
        self, within_days: int | None = None, limit: int = DEFAULT_LIMIT
    ) -> dict[str, Any]:
        limit = _limit(limit)
        within_days = _bounded("within_days", within_days, 0, MAX_DAYS)
        rows = self._reader.scheduled(within_days=within_days, limit=limit + 1)
        return _page(rows, limit)

    def get(self, download_id: int) -> dict[str, Any]:
        found = self._reader.get(download_id)
        if found is None:
            raise InvalidInput(f"No tracked download with id {download_id}.")
        return _view(found)

    def keep(self, download_id: int) -> dict[str, Any]:
        """Cancel a scheduled deletion ("keep this file")."""
        found = self._reader.get(download_id)
        if found is None:
            raise InvalidInput(f"No tracked download with id {download_id}.")
        if self._canceller.cancel(download_id):
            return {"kept": True, "id": download_id, "filename": clean_text(found.filename)}
        # Zero rows changed: it was not SCHEDULED (already deleted, already
        # cancelled, or the scheduler claimed it a moment ago).
        current = self._reader.get(download_id)
        return {
            "kept": False,
            "id": download_id,
            "reason": f"Deletion is not pending (current status: "
            f"{current.status if current else 'unknown'}).",
        }
