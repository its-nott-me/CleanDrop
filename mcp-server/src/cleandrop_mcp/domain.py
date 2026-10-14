"""Domain types and ports (interfaces). No I/O, no SQL, no MCP in here.

Everything else depends on this module; this module depends on nothing.
That direction is the Dependency Inversion Principle: the service layer
talks to `DownloadReader` / `DeletionCanceller`, never to SQLite.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence
from urllib.parse import urlparse


class DeleteStatus(str, Enum):
    """Values of `downloads.delete_status` written by CleanDrop today.

    NONE and DELETING are internal states and deliberately not exposed
    as search filters.
    """

    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"


class CleanDropError(Exception):
    """Base class for errors that are safe to show to the model."""


class InvalidInput(CleanDropError):
    pass


class DatabaseUnavailable(CleanDropError):
    pass


@dataclass(frozen=True, slots=True)
class Download:
    id: int
    filename: str
    path: str
    size_bytes: int | None
    mime_type: str | None
    url: str | None
    page_title: str | None
    status: str
    delete_after: str | None
    deleted_at: str | None
    created_at: str


def source_host(url: str | None) -> str | None:
    """Reduce a URL to its host.

    Full URLs routinely carry secrets (pre-signed S3 query strings,
    session tokens). The agent only needs to know *where* a file came
    from, so the rest never leaves this process.
    """
    if not url:
        return None
    try:
        host = urlparse(url).hostname
    except ValueError:
        return None
    return host.lower() if host else None


class DownloadReader(Protocol):
    """Read side. Implementations must not be able to write."""

    def search(
        self,
        *,
        terms: Sequence[str],
        status: DeleteStatus | None,
        since_days: int | None,
        limit: int,
    ) -> list[Download]: ...

    def scheduled(
        self, *, within_days: int | None, limit: int
    ) -> list[Download]: ...

    def get(self, download_id: int) -> Download | None: ...


class DeletionCanceller(Protocol):
    """Write side: the single mutation this server is allowed to make."""

    def cancel(self, download_id: int) -> bool:
        """Cancel a pending deletion. True only if a SCHEDULED row changed."""
        ...
