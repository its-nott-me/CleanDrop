import logging
import os
import sys
from pathlib import Path

from .repository import SqliteDeletionCanceller, SqliteDownloadReader
from .server import build_server
from .service import DownloadService


def default_db_path() -> Path:
    # Same location CleanDrop's companion uses (database.py: APP_DIR).
    override = os.environ.get("CLEANDROP_DB")
    return Path(override) if override else Path.home() / ".cleandrop" / "cleandrop.db"


def main() -> None:
    # stdout carries the MCP protocol; logs must go to stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    db_path = default_db_path()
    service = DownloadService(
        SqliteDownloadReader(db_path), SqliteDeletionCanceller(db_path)
    )
    build_server(service).run()  # stdio by default


if __name__ == "__main__":
    main()
