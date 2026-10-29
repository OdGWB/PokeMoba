"""Copia/incolla di testo negli appunti di sistema (per i codici di connessione).

Su Windows si usano direttamente le API Win32 via ctypes (affidabili con
qualsiasi testo); altrove si ripiega su tkinter. Nessuna dipendenza extra.
"""
from __future__ import annotations

import sys

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _win32():
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.OpenClipboard.restype = wintypes.BOOL
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    u32.GetClipboardData.restype = wintypes.HANDLE
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    return ctypes, u32, k32


def copy(text: str) -> bool:
    """True se il testo è finito negli appunti."""
    if sys.platform == "win32":
        try:
            ctypes, u32, k32 = _win32()
            data = text.encode("utf-16-le") + b"\x00\x00"
            if not u32.OpenClipboard(None):
                return False
            try:
                u32.EmptyClipboard()
                h = k32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                p = k32.GlobalLock(h)
                ctypes.memmove(p, data, len(data))
                k32.GlobalUnlock(h)
                return bool(u32.SetClipboardData(CF_UNICODETEXT, h))
            finally:
                u32.CloseClipboard()
        except Exception:
            pass
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        return False


def paste() -> str:
    if sys.platform == "win32":
        try:
            ctypes, u32, k32 = _win32()
            if not u32.OpenClipboard(None):
                return ""
            try:
                h = u32.GetClipboardData(CF_UNICODETEXT)
                if not h:
                    return ""
                p = k32.GlobalLock(h)
                try:
                    return ctypes.wstring_at(p)
                finally:
                    k32.GlobalUnlock(h)
            finally:
                u32.CloseClipboard()
        except Exception:
            pass
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return text
    except Exception:
        return ""
