from pathlib import Path

from ai.filename_model import suggest_filename
from database import update_current_path, update_ai_status


def _unique_path(path):

    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent

    counter = 2

    while True:

        candidate = parent / f"{stem} ({counter}){suffix}"

        if not candidate.exists():
            return candidate

        counter += 1


def process_ai_download(download):

    download_id = download["chrome_download_id"]

    try:

        print(
            f"[AI] Starting analysis: {download_id}"
        )

        context = {
            "path": download["current_path"],
            "filename": Path(download["current_path"]).name,
            "mime": download["mime_type"],
            "url": download["url"],
            "referrer": download["referrer"],
            "page_title": download["page_title"] or "",
            "page_description": download["page_description"] or ""
        }

        suggested = suggest_filename(context)

        print(
            f"[AI] Suggestion: {suggested}"
        )

        original_path = Path(context["path"])

        if suggested == original_path.name:

            print(
                f"[AI] No rename needed: {download_id}"
            )

        elif not original_path.is_file():

            print(
                f"[AI] File no longer exists, "
                f"skipping rename: {download_id}"
            )

        else:

            new_path = _unique_path(
                original_path.with_name(suggested)
            )

            original_path.rename(new_path)

            update_current_path(
                download_id,
                str(new_path)
            )

            print(
                f"[AI] Renamed to: {new_path}"
            )

        update_ai_status(download_id, "DONE")

    except Exception as error:

        print(
            f"[AI] ERROR: {error}"
        )

        update_ai_status(download_id, "ERROR")