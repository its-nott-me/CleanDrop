import ctypes
from ctypes import wintypes
from pathlib import Path


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


# ---------------------------------------------------------
# Windows constants
# ---------------------------------------------------------

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004

OPEN_EXISTING = 3

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

FileIdInfo = 18


# ---------------------------------------------------------
# Windows structures
# ---------------------------------------------------------

class FILE_ID_128(ctypes.Structure):
    _fields_ = [
        ("Identifier", ctypes.c_ubyte * 16)
    ]


class FILE_ID_INFO(ctypes.Structure):
    _fields_ = [
        ("VolumeSerialNumber", ctypes.c_ulonglong),
        ("FileId", FILE_ID_128)
    ]


# ---------------------------------------------------------
# Windows API definitions
# ---------------------------------------------------------

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE
]

kernel32.CreateFileW.restype = wintypes.HANDLE


kernel32.GetFileInformationByHandleEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.LPVOID,
    wintypes.DWORD
]

kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL


kernel32.CloseHandle.argtypes = [
    wintypes.HANDLE
]

kernel32.CloseHandle.restype = wintypes.BOOL


# ---------------------------------------------------------
# Public function
# ---------------------------------------------------------

def get_file_identity(path: str | Path) -> dict:
    """
    Return the Windows volume serial number and
    128-bit file ID for a file.
    """

    path = str(Path(path).resolve())

    handle = kernel32.CreateFileW(
        path,
        GENERIC_READ,

        FILE_SHARE_READ |
        FILE_SHARE_WRITE |
        FILE_SHARE_DELETE,

        None,
        OPEN_EXISTING,
        0,
        None
    )

    if handle == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()

        raise OSError(
            error,
            f"Could not open file: {path}"
        )

    try:

        info = FILE_ID_INFO()

        success = kernel32.GetFileInformationByHandleEx(
            handle,
            FileIdInfo,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )

        if not success:
            error = ctypes.get_last_error()

            raise OSError(
                error,
                f"Could not retrieve file identity: {path}"
            )

        file_id = bytes(info.FileId.Identifier).hex()

        volume_serial = str(info.VolumeSerialNumber)

        return {
            "volume_serial": volume_serial,
            "file_id": file_id,
            "identity_key": f"{volume_serial}:{file_id}"
        }

    finally:

        kernel32.CloseHandle(handle)


def identity_key(identity: dict) -> str:
    """
    Convert identity into a convenient database key.
    """

    return (
        f"{identity['volume_serial']}:"
        f"{identity['file_id']}"
    )