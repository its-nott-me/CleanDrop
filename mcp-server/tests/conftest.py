"""Fixtures build a database with CleanDrop's *real* schema and writer.

Rather than hand-copying CREATE TABLE, we import companion/database.py and
call its own initialize_database() / create_scheduled_download(). If the
companion's schema ever changes, these tests fail instead of the MCP server
silently drifting out of sync.
"""

import importlib
import sys
from pathlib import Path

import pytest

COMPANION = Path(__file__).resolve().parents[2] / "companion"


class Db:
    def __init__(self, module, path: Path) -> None:
        self.m = module
        self.path = path
        self._next_chrome_id = 1

    def add(
        self,
        filename="report.pdf",
        *,
        url="https://example.com/files/report.pdf?token=SECRET123",
        page_title="Quarterly Report",
        delete_after="2999-01-01T00:00:00.000Z",
        incognito=False,
    ) -> int:
        n = self._next_chrome_id
        self._next_chrome_id += 1
        self.m.create_scheduled_download(
            {
                "id": n,
                "filename": str(Path("C:/Users/me/Downloads") / filename),
                "url": url,
                "referrer": "https://example.com/",
                "page_title": page_title,
                "page_description": "desc",
                "mime": "application/pdf",
                "fileSize": 1234,
                "startTime": "2026-10-01T10:00:00Z",
                "endTime": "2026-10-01T10:00:05Z",
                "incognito": incognito,
            },
            {
                "volume_serial": "1",
                "file_id": f"{n:032x}",
                "identity_key": f"1:{n:032x}",
            },
            delete_after,
        )
        with self.m.get_connection() as conn:
            return conn.execute(
                "SELECT id FROM downloads WHERE chrome_download_id = ?", (n,)
            ).fetchone()["id"]


@pytest.fixture
def db(tmp_path, monkeypatch) -> Db:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.syspath_prepend(str(COMPANION))
    sys.modules.pop("database", None)
    module = importlib.import_module("database")
    module.initialize_database()
    yield Db(module, module.DB_PATH)
    sys.modules.pop("database", None)
