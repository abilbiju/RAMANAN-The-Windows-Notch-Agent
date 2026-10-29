import sys
import winreg
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from . import APP_NAME, STORAGE_NAME

DEFAULTS = {
    # appearance
    "scale": 1.0,               # whole-UI scale, applied on restart
    "idle_style": "pill",       # pill | slim | invisible
    "idle_width": 180,
    "accent_mode": "artwork",   # artwork | custom
    "accent_color": "#0a84ff",
    "visualizer": True,
    "mascot": "ramanan",        # ramanan | none — pixel character living in the notch
    "display": "",              # screen name; "" = primary
    "dock_edge": "top",         # top | bottom | left | right | float
    "dock_pos": 0.5,            # position along the docked edge (0..1)
    "float_x": 0.5,             # floating bubble centre, fraction of the screen
    "float_y": 0.35,
    "lock_position": False,     # disable dragging
    # behaviour
    "hover_delay": 140,         # ms before hovering expands the notch
    "hud_duration": 1.0,        # multiplier for how long HUDs stay up
    "hide_fullscreen": True,
    "compact_media": True,      # show the now-playing pill while music plays
    "default_tab": 0,
    "show_mirror": True,
    "lyrics": True,
    # which HUDs / live activities to show
    "hud_volume": True,
    "hud_brightness": True,
    "hud_locks": True,
    "hud_focus": True,
    "hud_battery": True,
    "hud_privacy": True,
    "hud_downloads": True,
    "hud_track": True,
}

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = APP_NAME
LEGACY_RUN_NAMES = ("WinNotch",)


class Settings(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._store = QSettings(STORAGE_NAME, STORAGE_NAME)

    def get(self, key):
        default = DEFAULTS[key]
        return self._store.value(key, default, type=type(default))

    def set(self, key, value):
        if value != self.get(key):
            self._store.setValue(key, value)
            self.changed.emit(key)

    def reset(self):
        for key in DEFAULTS:
            self._store.remove(key)
            self.changed.emit(key)


def _autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    main = Path(__file__).resolve().parents[1] / "main.py"
    return f'"{pythonw}" "{main}"'


def autostart_enabled():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        for name in (RUN_NAME, *LEGACY_RUN_NAMES):
            try:
                winreg.QueryValueEx(key, name)
                return True
            except OSError:
                pass
    return False


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name in LEGACY_RUN_NAMES:  # entries from before the rename
            try:
                winreg.DeleteValue(key, name)
            except OSError:
                pass
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except OSError:
                pass
