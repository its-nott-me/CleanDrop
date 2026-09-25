from pathlib import Path
import sqlite3


APP_DIR = Path.home() / ".cleandrop"
DB_PATH = APP_DIR / "cleandrop.db"


def get_connection():
    APP_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)

    connection.row_factory = sqlite3.Row

    # WAL avoids creating/deleting a journal file on every
    # transaction (the default rollback-journal mode does this),
    # which is expensive on Windows when antivirus real-time
    # scanning intercepts each small file create/delete.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")

    return connection


def initialize_database():

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                chrome_download_id INTEGER UNIQUE NOT NULL,

                original_path TEXT NOT NULL,
                current_path TEXT NOT NULL,

                original_filename TEXT NOT NULL,

                volume_serial TEXT NOT NULL,
                file_id TEXT NOT NULL,
                identity_key TEXT NOT NULL UNIQUE,

                url TEXT,
                referrer TEXT,

                page_title TEXT,
                page_description TEXT,

                mime_type TEXT,
                file_size INTEGER,

                start_time TEXT,
                end_time TEXT,

                incognito INTEGER NOT NULL DEFAULT 0,

                status TEXT NOT NULL DEFAULT 'COMPLETED',

                delete_after TEXT,
                delete_status TEXT NOT NULL DEFAULT 'NONE',
                deleted_at TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


def create_scheduled_download(download, identity, delete_after):
    """
    Creates a tracked download row. Only ever called at the moment
    a deletion is scheduled — a download the user never schedules
    is never written to the database at all, so SQLite doesn't
    accumulate rows for files nobody asked to track.
    """

    path = download["filename"]

    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO downloads (
                chrome_download_id,

                original_path,
                current_path,
                original_filename,

                volume_serial,
                file_id,
                identity_key,

                url,
                referrer,

                page_title,
                page_description,

                mime_type,
                file_size,

                start_time,
                end_time,

                incognito,

                status,

                delete_after,
                delete_status
            )
            VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?,
                ?,
                'SCHEDULED'
            )
        """, (
            download["id"],

            path,
            path,
            Path(path).name,

            identity["volume_serial"],
            identity["file_id"],
            identity["identity_key"],

            download.get("url"),
            download.get("referrer"),

            download.get("page_title"),
            download.get("page_description"),

            download.get("mime"),
            download.get("fileSize"),

            download.get("startTime"),
            download.get("endTime"),

            int(download.get("incognito", False)),

            "COMPLETED",

            delete_after
        ))

        conn.commit()


def get_expired_downloads():

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT *
            FROM downloads
            WHERE
                delete_status = 'SCHEDULED'
                AND delete_after IS NOT NULL
                AND datetime(delete_after) <= datetime('now')
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def update_delete_status(
    download_id,
    status
):

    with get_connection() as conn:

        conn.execute("""
            UPDATE downloads

            SET
                delete_status = ?,
                updated_at = CURRENT_TIMESTAMP,

                deleted_at =
                    CASE
                        WHEN ? = 'DELETED'
                        THEN CURRENT_TIMESTAMP
                        ELSE deleted_at
                    END

            WHERE id = ?
        """, (
            status,
            status,
            download_id
        ))

        conn.commit()


def get_recent_downloads(limit=20):

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT *
            FROM downloads
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def cancel_scheduled_download(download_id):
    with get_connection() as conn:

        cursor = conn.execute("""
            UPDATE downloads
            SET
                delete_status = 'CANCELLED',
                updated_at = CURRENT_TIMESTAMP
            WHERE
                id = ?
                AND delete_status = 'SCHEDULED'
        """, (
            download_id,
        ))

        conn.commit()

        return cursor.rowcount > 0


def get_scheduled_downloads():

    with get_connection() as conn:

        rows = conn.execute("""
            SELECT
                id,
                chrome_download_id,
                current_path,
                original_filename,
                file_size,
                url,
                delete_after,
                delete_status,
                created_at
            FROM downloads
            WHERE
                delete_status = 'SCHEDULED'
            ORDER BY delete_after ASC
        """).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def claim_download_for_deletion(download_id):

    with get_connection() as conn:

        cursor = conn.execute("""
            UPDATE downloads
            SET
                delete_status = 'DELETING',
                updated_at = CURRENT_TIMESTAMP
            WHERE
                id = ?
                AND delete_status = 'SCHEDULED'
                AND delete_after IS NOT NULL
                AND datetime(delete_after) <= datetime('now')
        """, (
            download_id,
        ))

        conn.commit()

        return cursor.rowcount > 0