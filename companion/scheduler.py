import time
from pathlib import Path
from datetime import datetime

from database import (
    get_expired_downloads,
    update_delete_status
)

from files.deletion import safely_recycle


CHECK_INTERVAL = 30


LOG_DIR = (
    Path.home()
    / ".cleandrop"
)

LOG_FILE = (
    LOG_DIR
    / "scheduler.log"
)


def log(message):

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    timestamp = (
        datetime.now().isoformat()
    )


    with LOG_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            f"[{timestamp}] {message}\n"
        )


def scheduler_loop():

    log(
        "Scheduler started"
    )


    while True:

        try:

            downloads = (
                get_expired_downloads()
            )


            for download in downloads:

                download_id = (
                    download["id"]
                )


                log(
                    "Processing expiry: "
                    f"{download_id}"
                )


                result = (
                    safely_recycle(
                        download
                    )
                )


                status = (
                    result["status"]
                )


                update_delete_status(
                    download_id,
                    status
                )


                log(
                    "Deletion result: "
                    f"{status}"
                )


                if result.get("reason"):

                    log(
                        "Reason: "
                        + result["reason"]
                    )


        except Exception as error:

            log(
                "Scheduler error: "
                + str(error)
            )


        time.sleep(
            CHECK_INTERVAL
        )