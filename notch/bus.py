from PySide6.QtCore import QObject, Signal


class Bus(QObject):
    """Signals emitted by the background services. Services run on worker
    threads; Qt queues these onto the UI thread automatically."""

    media = Signal(object)            # snapshot dict from MediaService
    lyrics = Signal(object, object)   # track key, [(seconds, line)] or None
    volume = Signal(float, bool)      # scalar 0..1, muted
    brightness = Signal(int)          # percent
    lock_key = Signal(str, bool)      # "Caps Lock" / "Num Lock", on
    focus = Signal(int)               # 0 off, 1 priority only, 2 alarms only
    battery = Signal(int, bool)       # percent, plugged in
    privacy = Signal(object)          # {"camera": [app, ...], "mic": [app, ...]}
    downloads = Signal(object)        # list of active download dicts
    download_done = Signal(str, str)  # file name, full path
    fullscreen = Signal(bool)         # a fullscreen app / presentation is active
