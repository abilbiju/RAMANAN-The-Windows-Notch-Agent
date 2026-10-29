"""Lock keys, Focus Assist / Do Not Disturb, battery, camera & mic usage,
fullscreen detection and WMI-driven brightness events."""

import ctypes
import logging
import os
import sys
import threading
import winreg
from pathlib import Path

import psutil

from .. import APP_NAME
from .base import Poller

log = logging.getLogger(__name__)


class LockKeys(Poller):
    interval = 0.08
    KEYS = {"Caps Lock": 0x14, "Num Lock": 0x90}

    def setup(self):
        self._user32 = ctypes.windll.user32
        self._state = {name: self._read(vk) for name, vk in self.KEYS.items()}

    def _read(self, vk):
        return bool(self._user32.GetKeyState(vk) & 1)

    def tick(self):
        for name, vk in self.KEYS.items():
            on = self._read(vk)
            if on != self._state[name]:
                self._state[name] = on
                self.bus.lock_key.emit(name, on)


# Undocumented but long-stable WNF state that the shell updates whenever
# Focus Assist / Do Not Disturb changes profile.
WNF_SHEL_QUIETHOURS_ACTIVE_PROFILE_CHANGED = 0x0D83063EA3BF1C75


class FocusAssist(Poller):
    interval = 1.0

    def setup(self):
        self._ntdll = ctypes.WinDLL("ntdll")
        self._last = self._read()

    def _read(self):
        state = ctypes.c_ulonglong(WNF_SHEL_QUIETHOURS_ACTIVE_PROFILE_CHANGED)
        stamp = ctypes.c_ulong(0)
        value = ctypes.c_uint32(0)
        size = ctypes.c_ulong(ctypes.sizeof(value))
        status = self._ntdll.NtQueryWnfStateData(
            ctypes.byref(state), None, None,
            ctypes.byref(stamp), ctypes.byref(value), ctypes.byref(size))
        if status != 0:
            raise OSError(f"NtQueryWnfStateData failed: {status & 0xFFFFFFFF:#x}")
        return value.value

    def tick(self):
        profile = self._read()
        if profile != self._last:
            self._last = profile
            self.bus.focus.emit(profile)


class Battery(Poller):
    interval = 2.0

    def setup(self):
        if psutil.sensors_battery() is None:
            raise RuntimeError("no battery")
        self._last = None

    def tick(self):
        b = psutil.sensors_battery()
        state = (round(b.percent), bool(b.power_plugged))
        if state != self._last:
            self._last = state
            self.bus.battery.emit(*state)


CONSENT_STORE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"
OWN_EXE = sys.executable.replace("\\", "#").lower()


def _subkeys(key):
    i = 0
    while True:
        try:
            yield winreg.EnumKey(key, i)
        except OSError:
            return
        i += 1


def _in_use(parent, sub):
    try:
        with winreg.OpenKey(parent, sub) as k:
            start, _ = winreg.QueryValueEx(k, "LastUsedTimeStart")
            stop, _ = winreg.QueryValueEx(k, "LastUsedTimeStop")
    except OSError:
        return False
    return start > 0 and stop == 0


def _pretty_packaged(name):
    # "Microsoft.WindowsCamera_8wekyb3d8bbwe" -> "Windows Camera"
    base = name.split("_")[0].split(".")[-1]
    out = "".join(" " + c if c.isupper() and i and not base[i - 1].isupper() else c
                  for i, c in enumerate(base))
    return out.strip() or name


def _pretty_exe(name):
    if name.lower() == OWN_EXE:
        return APP_NAME
    return Path(name.replace("#", "\\")).stem


class Privacy(Poller):
    """Camera / microphone usage, read from the same registry store that
    drives the Windows privacy indicator in the taskbar."""

    interval = 1.0

    def setup(self):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, CONSENT_STORE).Close()
        self._last = None

    def _scan(self, capability):
        apps = []
        try:
            root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, CONSENT_STORE + "\\" + capability)
        except OSError:
            return apps
        with root:
            for sub in _subkeys(root):
                if sub == "NonPackaged":
                    with winreg.OpenKey(root, sub) as np:
                        apps += [_pretty_exe(s) for s in _subkeys(np) if _in_use(np, s)]
                elif _in_use(root, sub):
                    apps.append(_pretty_packaged(sub))
        return sorted(set(apps))

    def tick(self):
        state = {"camera": self._scan("webcam"), "mic": self._scan("microphone")}
        if state != self._last:
            self._last = state
            self.bus.privacy.emit(state)


class Fullscreen(Poller):
    interval = 1.0
    BUSY_STATES = (2, 3, 4)  # QUNS_BUSY, QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
    # Windows reports QUNS_BUSY while the desktop itself is in front (Win+D /
    # everything minimised) because the desktop window covers the screen.
    NOT_FULLSCREEN = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

    def setup(self):
        self._last = None

    def _foreground_class(self):
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(user32.GetForegroundWindow(), buf, 64)
        return buf.value

    def tick(self):
        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return
        busy = state.value in self.BUSY_STATES and self._foreground_class() not in self.NOT_FULLSCREEN
        if busy != self._last:
            self._last = busy
            self.bus.fullscreen.emit(busy)


WBEM_E_TIMED_OUT = -2147209215  # 0x80043001


class WmiWatcher(threading.Thread):
    """Blocks on a WMI event query and hands each event to `handler`."""

    def __init__(self, bus, namespace, query, handler):
        super().__init__(daemon=True, name=f"WMI:{query.split()[-1]}")
        self.bus = bus
        self.namespace = namespace
        self.query = query
        self.handler = handler
        self._halt = threading.Event()

    def run(self):
        import pythoncom
        import pywintypes
        import win32com.client
        pythoncom.CoInitialize()
        try:
            self.service = win32com.client.GetObject(f"winmgmts:{self.namespace}")
            events = self.service.ExecNotificationQuery(self.query)
        except Exception as exc:
            log.info("%s unavailable: %s", self.name, exc)
            return
        while not self._halt.is_set():
            try:
                event = events.NextEvent(500)
            except pywintypes.com_error as exc:
                if exc.excepinfo and exc.excepinfo[5] == WBEM_E_TIMED_OUT:
                    continue
                log.warning("%s stopped: %s", self.name, exc)
                return
            try:
                self.handler(self, event)
            except Exception:
                log.exception("%s handler failed", self.name)

    def stop(self):
        self._halt.set()


def _on_brightness(watcher, event):
    watcher.bus.brightness.emit(int(event.Brightness))


def brightness_watcher(bus):
    return WmiWatcher(bus, "root/WMI", "SELECT * FROM WmiMonitorBrightnessEvent", _on_brightness)


def downloads_dir():
    try:
        from pywintypes import IID
        from win32com.shell import shell
        return Path(shell.SHGetKnownFolderPath(IID("{374DE290-123F-4565-9164-39C4925E467B}")))
    except Exception:
        return Path(os.path.expanduser("~/Downloads"))
