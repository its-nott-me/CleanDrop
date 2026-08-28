from pathlib import Path

from .identity import get_file_identity
from .recycle import move_to_recycle_bin


def safely_recycle(download):

    path = Path(
        download["current_path"]
    )

    expected_identity = (
        download["identity_key"]
    )


    # --------------------------------------------------
    # 1. Path must exist
    # --------------------------------------------------

    if not path.exists():

        return {
            "status": "NOT_FOUND",
            "path": str(path)
        }


    # --------------------------------------------------
    # 2. Get the identity of what currently exists
    # --------------------------------------------------

    try:

        actual_identity = get_file_identity(path)

    except OSError as error:

        return {
            "status": "FAILED",
            "path": str(path),
            "reason": str(error)
        }


    actual_key = (
        actual_identity["identity_key"]
    )


    # --------------------------------------------------
    # 3. CRITICAL SAFETY CHECK
    # --------------------------------------------------

    if actual_key != expected_identity:

        return {
            "status": "IDENTITY_MISMATCH",
            "path": str(path),

            "expected_identity":
                expected_identity,

            "actual_identity":
                actual_key
        }


    # --------------------------------------------------
    # 4. Identity matches → recycle
    # --------------------------------------------------

    try:

        move_to_recycle_bin(path)

    except Exception as error:

        return {
            "status": "FAILED",
            "path": str(path),
            "reason": str(error)
        }


    # --------------------------------------------------
    # 5. Verify it disappeared from original location
    # --------------------------------------------------

    if path.exists():

        return {
            "status": "FAILED",
            "path": str(path),
            "reason":
                "Recycle operation returned but "
                "file still exists"
        }


    return {
        "status": "DELETED",
        "path": str(path)
    }