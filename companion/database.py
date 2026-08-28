from pathlib import Path
import sqlite3


APP_DIR = Path.home() / ".cleandrop"
DB_PATH = APP_DIR / "cleandrop.db"


def get_connection():
    APP_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)

    connection.row_factory = sqlite3.Row

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


def save_download(download, identity):
    with get_connection() as conn:

        path = download["filename"]

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
                ?, ?
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

            download.get("mime"),
            download.get("fileSize"),

            download.get("startTime"),
            download.get("endTime"),

            int(download.get("incognito", False)),

            "COMPLETED",

            download.get("deleteAfter"),

            (
                "SCHEDULED"
                if download.get("deleteAfter")
                else "NONE"
            )
        ))

        conn.commit()

        path = download["filename"]

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

                mime_type,
                file_size,

                start_time,
                end_time,

                incognito,

                status

            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

            download.get("mime"),
            download.get("fileSize"),

            download.get("startTime"),
            download.get("endTime"),

            int(download.get("incognito", False)),

            "COMPLETED"
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