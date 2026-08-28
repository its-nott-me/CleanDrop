from pathlib import Path
from typing import Optional

from .identity import get_file_identity


class ResolveResult:
    def __init__(
        self,
        status: str,
        path: Optional[str] = None,
        reason: Optional[str] = None
    ):
        self.status = status
        self.path = path
        self.reason = reason

    def __repr__(self):
        return (
            f"ResolveResult("
            f"status={self.status!r}, "
            f"path={self.path!r}, "
            f"reason={self.reason!r})"
        )


def resolve_at_path(
    path: str,
    expected_identity: str
) -> ResolveResult:

    path_obj = Path(path)

    if not path_obj.exists():
        return ResolveResult(
            status="NOT_FOUND",
            path=None,
            reason="Path does not exist"
        )

    try:
        identity = get_file_identity(path_obj)

    except OSError as exc:
        return ResolveResult(
            status="ERROR",
            path=None,
            reason=str(exc)
        )

    actual_identity = identity["identity_key"]

    if actual_identity != expected_identity:

        return ResolveResult(
            status="IDENTITY_MISMATCH",
            path=str(path_obj),
            reason=(
                f"Expected {expected_identity}, "
                f"found {actual_identity}"
            )
        )

    return ResolveResult(
        status="FOUND",
        path=str(path_obj)
    )