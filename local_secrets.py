"""Small Windows DPAPI wrapper for secrets stored in the local user profile."""
import base64
import ctypes
import os
from ctypes import wintypes


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(value):
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    return _DataBlob(len(raw), buffer), buffer


def protect_text(value):
    """Return a base64 DPAPI-protected value, or None when unavailable."""
    if os.name != "nt" or not value:
        return None
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR,
                                         ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                                         ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, source_buffer = _blob(value)
    output = _DataBlob()
    if not crypt32.CryptProtectData(ctypes.byref(source), "Spotlight local remember-me",
                                    None, None, None, 0, ctypes.byref(output)):
        return None
    try:
        protected = ctypes.string_at(output.pbData, output.cbData)
        return base64.b64encode(protected).decode("ascii")
    finally:
        kernel32.LocalFree(output.pbData)


def unprotect_text(value):
    """Decode a DPAPI-protected value for the current Windows user, or None."""
    if os.name != "nt" or not value:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return None
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob),
                                           ctypes.POINTER(wintypes.LPWSTR),
                                           ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                                           ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, source_buffer = _blob(raw)
    output = _DataBlob()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0,
                                      ctypes.byref(output)):
        return None
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    except UnicodeDecodeError:
        return None
    finally:
        kernel32.LocalFree(output.pbData)
