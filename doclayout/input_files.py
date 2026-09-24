"""Validate API-selected file handles before reading their contents."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path


def _windows_open(path):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    get_type = kernel.GetFileType
    get_type.argtypes = [wintypes.HANDLE]
    get_type.restype = wintypes.DWORD
    get_path = kernel.GetFinalPathNameByHandleW
    get_path.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    get_path.restype = wintypes.DWORD
    # Deny writers/deletion; open the final reparse point itself, never its target.
    handle = create(str(path), 0x80000000, 1, None, 3, 0x00200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError("Input could not be opened safely.")
    try:
        if get_type(handle) != 1:
            raise ValueError("Input must be a regular disk file.")
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_path(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise ValueError("Input path could not be verified.")
        final = buffer.value
        if not final.startswith("\\\\?\\") or final.startswith("\\\\?\\UNC\\"):
            raise ValueError("Input must be a local file.")
        final = Path(final[4:])
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None
        return fd, final
    finally:
        if handle is not None:
            close(handle)


@contextmanager
def input_file(name, root):
    if root is None or not name or "\x00" in name:
        raise ValueError("Filepath access is not allowed.")
    candidate = Path(name)
    if name.startswith(("\\\\", "//")) or ".." in candidate.parts:
        raise ValueError("Filepath access is not allowed.")
    tail = name[len(candidate.drive) :]
    if ":" in tail or (candidate.drive and not candidate.is_absolute()):
        raise ValueError("Filepath access is not allowed.")
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve(strict=True)
    if not candidate.is_relative_to(root):
        raise ValueError("Filepath access is not allowed.")
    if os.name == "nt":
        fd, final = _windows_open(candidate)
    else:
        fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            final = Path(f"/proc/self/fd/{fd}").resolve(strict=True)
        except BaseException:
            os.close(fd)
            raise
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400
            or not final.is_relative_to(root)
        ):
            raise ValueError("Filepath access is not allowed.")
        yield source
