import ctypes
from ctypes import wintypes
from pathlib import Path


shell32 = ctypes.WinDLL("shell32", use_last_error=True)


# SHFileOperation constants
FO_DELETE = 0x0003

FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400
FOF_NOCONFIRMMKDIR = 0x0200

# Used to avoid displaying UI.
FLAGS = (
    FOF_ALLOWUNDO
    | FOF_NOCONFIRMATION
    | FOF_NOERRORUI
    | FOF_NOCONFIRMMKDIR
)


class SHFILEOPSTRUCTW(ctypes.Structure):

    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


shell32.SHFileOperationW.argtypes = [
    ctypes.POINTER(SHFILEOPSTRUCTW)
]

shell32.SHFileOperationW.restype = ctypes.c_int


def move_to_recycle_bin(path: str | Path) -> None:

    path = str(Path(path).resolve())

    if not Path(path).is_file():
        raise FileNotFoundError(
            f"File does not exist: {path}"
        )

    # SHFileOperation requires a double-null
    # terminated string.
    source = path + "\0\0"

    operation = SHFILEOPSTRUCTW()

    operation.hwnd = None
    operation.wFunc = FO_DELETE
    operation.pFrom = source
    operation.pTo = None
    operation.fFlags = FLAGS
    operation.fAnyOperationsAborted = False
    operation.hNameMappings = None
    operation.lpszProgressTitle = None

    result = shell32.SHFileOperationW(
        ctypes.byref(operation)
    )

    if result != 0:

        raise OSError(
            result,
            f"Failed to recycle file: {path}"
        )

    if operation.fAnyOperationsAborted:

        raise RuntimeError(
            f"Recycle operation was aborted: {path}"
        )