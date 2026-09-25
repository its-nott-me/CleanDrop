import time
from pathlib import Path
from datetime import datetime

from database import (
    get_expired_downloads,
    update_delete_status,
    claim_download_for_deletion
)

from files.deletion import safely_recycle
from llm_manager import ensure_llm_server_running


CHECK_INTERVAL = 30
LLM_CHECK_INTERVAL = 15


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


                # Atomically claim the deletion.
                # If the user cancelled it after we fetched
                # the expired rows, this returns False and
                # we must NOT delete the file.
                if not claim_download_for_deletion(
                    download_id
                ):
                    log(
                        f"Skipping {download_id}: "
                        "no longer scheduled"
                    )
                    continue


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


def llm_watchdog_loop():

    log(
        "LLM watchdog started"
    )


    while True:

        try:

            ensure_llm_server_running(
                log=log
            )

        except Exception as error:

            log(
                "LLM watchdog error: "
                + str(error)
            )


        time.sleep(
            LLM_CHECK_INTERVAL
        )