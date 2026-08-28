import time
from database import (get_expired_downloads, update_delete_status)
from files.deletion import safely_recycle

CHECK_INTERVAL = 5

from pathlib import Path
from datetime import datetime

LOG_DIR = Path.home() / ".cleandrop"
LOG_FILE = LOG_DIR / "scheduler.log"

def log(message):

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().isoformat()

    with LOG_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            f"[{timestamp}] {message}\n"
        )

def scheduler_loop():

    log("Scheduler started")

    while True:

        try:

            downloads = (
                get_expired_downloads()
            )


            for download in downloads:

                log(
                    "Processing expiry: "
                    f"{download['identity_key']}"
                )


                result = safely_recycle(
                    download
                )


                status = result["status"]


                update_delete_status(
                    download["id"],
                    status
                )


                log(
                    f"Deletion result: {status}"
                )


        except Exception as error:

            log(
                "Scheduler error: "
                + str(error)
            )


        time.sleep(
            CHECK_INTERVAL
        )