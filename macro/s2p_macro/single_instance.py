"""One S2P-Joystick-Macro per user session.

A second launch (double-clicking the EXE again, or "Open" in S2P) signals the
running copy to show its window and exits; the running copy may be hidden in
the notification area while it keeps serving controller triggers.
"""

from __future__ import annotations

import ctypes
import sys
import threading

EVENT_NAME = "Local\\S2P-Joystick-Macro.Show"
ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0
ASFW_ANY = 0xFFFFFFFF


def allow_foreground_handoff():
    """Let the running copy take the foreground when it shows its window.

    Windows only lets the foreground process (or one it just started) bring a
    window to the front.  This second copy was started by S2P's Open button or
    a double-click, so it may; the running copy in the background may not.
    Passing the right on before signalling makes the shown window come to the
    front with focus instead of only flashing on the taskbar.
    """
    try:
        user32 = ctypes.WinDLL("user32")
        user32.AllowSetForegroundWindow.argtypes = (ctypes.c_ulong,)
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except (AttributeError, OSError):
        pass


class SingleInstance:
    def __init__(self, on_show, name=EVENT_NAME):
        self._on_show = on_show
        self._name = name
        self._event = None
        self._stop = None
        self._thread = None
        self.primary = True

    def acquire(self):
        """True for the first copy; False after waking the existing one."""
        if sys.platform != "win32":
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateEventW.restype = ctypes.c_void_p
        kernel32.CreateEventW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p)
        kernel32.SetEvent.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel32.WaitForMultipleObjects.argtypes = (
            ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_ulong,
        )
        kernel32.WaitForMultipleObjects.restype = ctypes.c_ulong
        self._kernel32 = kernel32
        event = kernel32.CreateEventW(None, False, False, self._name)
        if not event:
            return True  # cannot coordinate; just run
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            allow_foreground_handoff()
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)
            self.primary = False
            return False
        self._event = event
        self._stop = kernel32.CreateEventW(None, True, False, None)
        self._thread = threading.Thread(target=self._watch, name="S2P-MacroInstance", daemon=True)
        self._thread.start()
        return True

    def _watch(self):
        handles = (ctypes.c_void_p * 2)(self._event, self._stop)
        while True:
            result = self._kernel32.WaitForMultipleObjects(2, handles, False, 0xFFFFFFFF)
            if result != WAIT_OBJECT_0:
                return
            self._on_show()

    def release(self):
        if self._stop:
            self._kernel32.SetEvent(self._stop)
            if self._thread is not None:
                self._thread.join(1.0)
            self._kernel32.CloseHandle(self._stop)
            self._stop = None
        if self._event:
            self._kernel32.CloseHandle(self._event)
            self._event = None
