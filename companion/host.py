import sys
import json
import struct
import time


# Bump this string whenever you make a meaningful change to this
# file and rebuild. It's included in every response, so a stale
# exe is immediately visible in the console log (e.g. missing a
# field you just added) instead of something you have to infer.
HOST_BUILD = "2026-09-25-v1"

from pathlib import Path
from datetime import datetime

from database import (
    initialize_database,
    create_scheduled_download,
    cancel_scheduled_download,
    get_scheduled_downloads
)

from files.identity import get_file_identity
from ai.filename_model import suggest_filename


def read_message():

    raw_length = sys.stdin.buffer.read(4)

    if not raw_length:
        return None

    message_length = struct.unpack(
        "<I",
        raw_length
    )[0]

    message = sys.stdin.buffer.read(
        message_length
    )

    if len(message) != message_length:
        raise RuntimeError(
            "Incomplete message received."
        )

    return json.loads(
        message.decode("utf-8")
    )


def send_message(message):

    encoded = json.dumps(
        message
    ).encode("utf-8")

    sys.stdout.buffer.write(
        struct.pack(
            "<I",
            len(encoded)
        )
    )

    sys.stdout.buffer.write(
        encoded
    )

    sys.stdout.buffer.flush()


# ============================================================
# SUGGEST FILENAME (AI fallback, called before the file exists)
# ============================================================

def handle_suggest_filename(message):
    """
    Called from onDeterminingFilename, before the file is written
    to disk. Blocks on the LLM call and only responds once it's
    done — this is safe here (unlike the old post-download AI
    loop) because we're delaying a response, not trying to keep
    working after one has already been sent.
    """

    handler_start = time.perf_counter()

    context = {
        "filename": message.get("filename", ""),
        "mime": message.get("mime"),
        "url": message.get("url"),
        "referrer": message.get("referrer"),
        "page_title": message.get("page_title", ""),
        "page_description": message.get("page_description", "")
    }

    try:

        llm_start = time.perf_counter()

        suggested = suggest_filename(context)

        llm_elapsed_ms = (
            time.perf_counter() - llm_start
        ) * 1000

        handler_elapsed_ms = (
            time.perf_counter() - handler_start
        ) * 1000

        print(
            "[CleanDrop] AI suggested filename: "
            f"{suggested} (llm_call={llm_elapsed_ms:.0f}ms, "
            f"handler_total={handler_elapsed_ms:.0f}ms)",
            file=sys.stderr
        )

        return {
            "status": "success",
            "suggested_filename": suggested,
            "host_build": HOST_BUILD,
            "timing": {
                "llm_call_ms": round(llm_elapsed_ms, 1),
                "handler_total_ms": round(handler_elapsed_ms, 1)
            }
        }

    except Exception as error:

        handler_elapsed_ms = (
            time.perf_counter() - handler_start
        ) * 1000

        # Local LLM down, slow past its timeout, malformed
        # response, etc. — fail soft. The download must never
        # hang waiting on this; falling back to the original
        # filename is always an acceptable outcome.
        print(
            f"[CleanDrop] AI suggestion failed after "
            f"{handler_elapsed_ms:.0f}ms: {error}",
            file=sys.stderr
        )

        return {
            "status": "error",
            "suggested_filename": None,
            "host_build": HOST_BUILD,
            "timing": {
                "handler_total_ms": round(handler_elapsed_ms, 1)
            }
        }


# ============================================================
# SCHEDULE DELETION
# ============================================================

def handle_schedule_deletion(message):

    path = message.get("filename")

    if not path:

        return {
            "status": "error",
            "message": "schedule_deletion requires filename"
        }


    if not Path(path).exists():

        return {
            "status": "error",
            "message": "File does not exist"
        }


    delete_after = message.get("deleteAfter")

    if not delete_after:

        return {
            "status": "error",
            "message": "schedule_deletion requires deleteAfter"
        }


    # Validate the timestamp before writing it.
    try:

        datetime.fromisoformat(
            delete_after.replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:

        return {
            "status": "error",
            "message":
                "Invalid deleteAfter timestamp"
        }


    identity = get_file_identity(path)

    create_scheduled_download(
        message,
        identity,
        delete_after
    )


    print(
        "[CleanDrop] Deletion scheduled: "
        f"{path}, delete_after={delete_after}",
        file=sys.stderr
    )

    print(
        "[CleanDrop] File ID: "
        f"{identity['identity_key']}",
        file=sys.stderr
    )


    return {
        "status": "success",
        "message": "Deletion scheduled",
        "download_id": message.get("id"),
        "delete_after": delete_after
    }


def handle_cancel_deletion(message):

    download_id = message.get("id")

    if download_id is None:

        return {
            "status": "error",
            "message": "cancel_deletion requires id"
        }

    cancelled = cancel_scheduled_download(
        download_id
    )

    if not cancelled:

        return {
            "status": "error",
            "message":
                "Scheduled deletion not found or already processed"
        }

    print(
        "[CleanDrop] Deletion cancelled: "
        f"{download_id}",
        file=sys.stderr
    )

    return {
        "status": "success",
        "message": "Deletion cancelled",
        "id": download_id
    }


def handle_list_scheduled_deletions():

    downloads = get_scheduled_downloads()

    return {
        "status": "success",
        "downloads": downloads
    }


# ============================================================
# EVENT DISPATCHER
# ============================================================

def handle_message(message):

    event = message.get(
        "event"
    )


    if event == "suggest_filename":

        return handle_suggest_filename(
            message
        )


    if event == "schedule_deletion":

        return handle_schedule_deletion(
            message
        )


    if event == "cancel_deletion":

        return handle_cancel_deletion(
            message
        )


    if event == "list_scheduled_deletions":
        
        return handle_list_scheduled_deletions()


    return {
        "status": "error",
        "message":
            f"Unknown event: {event}"
    }


# ============================================================
# MAIN
# ============================================================

def main():

    initialize_database()


    print(
        "[CleanDrop] Native host started",
        file=sys.stderr
    )


    while True:

        message = read_message()


        if message is None:
            break


        try:

            response = handle_message(
                message
            )

            send_message(
                response
            )


        except Exception as error:

            print(
                f"[CleanDrop] ERROR: {error}",
                file=sys.stderr
            )


            send_message({
                "status": "error",
                "message": str(error)
            })


    print(
        "[CleanDrop] Host exiting",
        file=sys.stderr,
        flush=True
    )


if __name__ == "__main__":

    main()