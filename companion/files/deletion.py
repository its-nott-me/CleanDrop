from pathlib import Path

from files.identity import get_file_identity
from files.recycle import move_to_recycle_bin


def safely_recycle(download):

    path = Path(
        download["current_path"]
    )


    expected_identity = (
        download["identity_key"]
    )


    # ==================================================
    # 1. FILE MUST EXIST
    # ==================================================

    if not path.is_file():

        return {
            "status": "NOT_FOUND",
            "path": str(path)
        }


    # ==================================================
    # 2. READ CURRENT FILE IDENTITY
    # ==================================================

    try:

        actual_identity = (
            get_file_identity(path)
        )

    except Exception as error:

        return {
            "status": "FAILED",
            "path": str(path),
            "reason": str(error)
        }


    actual_key = (
        actual_identity["identity_key"]
    )


    # ==================================================
    # 3. CRITICAL SAFETY CHECK
    # ==================================================

    if actual_key != expected_identity:

        return {
            "status": "IDENTITY_MISMATCH",

            "path": str(path),

            "expected_identity":
                expected_identity,

            "actual_identity":
                actual_key
        }


    # ==================================================
    # 4. RECYCLE THE FILE
    # ==================================================

    try:

        move_to_recycle_bin(path)

    except Exception as error:

        return {
            "status": "FAILED",

            "path": str(path),

            "reason": str(error)
        }


    # ==================================================
    # 5. VERIFY ORIGINAL PATH IS GONE
    # ==================================================

    if path.exists():

        return {
            "status": "FAILED",

            "path": str(path),

            "reason":
                "File still exists after "
                "Recycle Bin operation"
        }


    return {
        "status": "DELETED",

        "path": str(path)
    }