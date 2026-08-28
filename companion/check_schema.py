import sqlite3

from database import DB_PATH


with sqlite3.connect(DB_PATH) as conn:

    rows = conn.execute(
        "PRAGMA table_info(downloads)"
    ).fetchall()

    for row in rows:
        print(
            f"{row[1]:20} "
            f"type={row[2]:10} "
            f"not_null={row[3]} "
            f"default={row[4]}"
        )