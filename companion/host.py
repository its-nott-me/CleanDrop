import sys
import json
import struct
import threading

from database import initialize_database, save_download

from pathlib import Path

from files.identity import get_file_identity

from datetime import datetime, timedelta, timezone

from scheduler import scheduler_loop

def read_message():
    raw_length = sys.stdin.buffer.read(4)

    if not raw_length:
        return None

    message_length = struct.unpack("<I", raw_length)[0]

    message = sys.stdin.buffer.read(message_length)

    if len(message) != message_length:
        raise RuntimeError("Incomplete message received.")

    return json.loads(message.decode("utf-8"))


def send_message(message):
    encoded = json.dumps(message).encode("utf-8")

    sys.stdout.buffer.write(
        struct.pack("<I", len(encoded))
    )

    sys.stdout.buffer.write(encoded)

    sys.stdout.buffer.flush()


def handle_message(message):

    event = message.get("event")

    if event != "download_completed":
        return {
            "status": "error",
            "message": f"Unknown event: {event}"
        }

    path = message.get("filename")

    if not path:
        return {
            "status": "error",
            "message": "Download has no file path"
        }

    if not Path(path).exists():
        return {
            "status": "error",
            "message": "Downloaded file does not exist"
        }

    identity = get_file_identity(path)

    delete_after = None

    if message.get("temporary"):

        expiry_seconds = message.get(
            "expirySeconds"
        )

        if not expiry_seconds:
            raise ValueError(
                "Temporary download has no expiry"
            )

        delete_after = (
            datetime.now(timezone.utc)
            + timedelta(seconds=expiry_seconds)
        ).isoformat()

    message["deleteAfter"] = delete_after

    save_download(
        message,
        identity
    )

    print(
        f"[CleanDrop] Saved: {path}",
        file=sys.stderr
    )

    print(
        f"[CleanDrop] File ID: {identity['identity_key']}",
        file=sys.stderr
    )

    return {
        "status": "success",
        "message": "Download saved",
        "download_id": message.get("id"),
        "identity": identity["identity_key"]
    }


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

            response = handle_message(message)

            send_message(response)

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