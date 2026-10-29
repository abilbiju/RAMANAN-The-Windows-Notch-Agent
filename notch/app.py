import argparse
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QProcess, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import APP_NAME, FULL_NAME, STORAGE_NAME, TAGLINE
from .bus import Bus
from .services.audio import Audio
from .services.downloads import Downloads
from .services.lyrics import Lyrics
from .services.media import MediaService
from .services.system import Battery, FocusAssist, Fullscreen, LockKeys, Privacy, brightness_watcher
from .settings import DEFAULTS, Settings
from .ui.expanded import DATA_DIR, dark_menu
from .ui.settings_window import SettingsWindow
from .ui.theme import G
from .ui.window import NotchWindow

log = logging.getLogger("winnotch")

RESTART_CODE = 1000


def resource(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / name


def app_icon():
    path = resource("winnotch.ico")
    if path.exists():
        return QIcon(str(path))
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1c1c1e"))
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setBrush(QColor(0, 0, 0))
    p.drawRoundedRect(14, 8, 36, 14, 7, 7)
    p.setBrush(QColor("#30d158"))
    p.drawEllipse(40, 12, 6, 6)
    p.end()
    return QIcon(pix)


def _demo(bus):
    """Replays every HUD so they can be previewed without real events."""
    events = [
        lambda: bus.volume.emit(0.42, False),
        lambda: bus.volume.emit(0.58, False),
        lambda: bus.brightness.emit(70),
        lambda: bus.lock_key.emit("Caps Lock", True),
        lambda: bus.focus.emit(1),
        lambda: bus.battery.emit(64, False),
        lambda: bus.battery.emit(64, True),
        lambda: bus.privacy.emit({"camera": ["Teams"], "mic": ["Teams"]}),
        lambda: bus.downloads.emit([{"name": "ubuntu-24.04-desktop-amd64.iso", "size": 734_003_200,
                                     "speed": 9_400_000}]),
        lambda: bus.downloads.emit([]),
        lambda: bus.download_done.emit("ubuntu-24.04-desktop-amd64.iso", str(DATA_DIR)),
        lambda: bus.privacy.emit({"camera": [], "mic": []}),
        lambda: bus.lock_key.emit("Caps Lock", False),
        lambda: bus.focus.emit(0),
    ]
    bus.privacy.emit({"camera": [], "mic": []})
    bus.battery.emit(64, True)
    for i, fire in enumerate(events):
        QTimer.singleShot(1500 + i * 2400, fire)


def _setup_logging():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(DATA_DIR / "winnotch.log", encoding="utf-8")]
    if sys.stderr is not None:  # pythonw / windowed exe have no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _restart_command():
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, [str(Path(__file__).resolve().parents[1] / "main.py")]


def main():
    parser = argparse.ArgumentParser(description=FULL_NAME)
    parser.add_argument("--demo", action="store_true", help="replay all HUDs once at startup")
    parser.add_argument("--settings", action="store_true", help="open the settings window at startup")
    args = parser.parse_args()
    _setup_logging()

    # The UI scale has to be known before the QApplication exists.
    scale = QSettings(STORAGE_NAME, STORAGE_NAME).value("scale", DEFAULTS["scale"], type=float)
    if scale != 1.0:
        os.environ["QT_SCALE_FACTOR"] = str(scale)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    lock = QLockFile(str(Path(tempfile.gettempdir()) / "winnotch.lock"))
    if not lock.tryLock(100):
        log.info("%s is already running", APP_NAME)
        return 0

    bus = Bus()
    settings = Settings()
    media = MediaService(bus)
    audio = Audio(bus)
    lyrics = Lyrics(bus)
    window = NotchWindow(bus, media, audio, lyrics, settings)
    settings_window = SettingsWindow(settings)

    def open_settings():
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    def restart():
        app.exit(RESTART_CODE)

    window.open_settings = open_settings
    settings_window.restart_requested.connect(restart)
    settings_window.preview_requested.connect(
        lambda: window.show_hud(None, ("glyph", G.CHECK, window.accent), f"{APP_NAME} is running",
                                "This is how notifications look", bar=0.65, color=window.accent,
                                value="65", duration=2500))

    services = [media, audio, LockKeys(bus), FocusAssist(bus), Battery(bus), Privacy(bus),
                Fullscreen(bus), Downloads(bus), brightness_watcher(bus)]
    if args.demo:
        _demo(bus)
    for service in services:
        service.start()
    window.show()

    # Notification-area icon: shows the app is running in the background.
    tray = QSystemTrayIcon(app_icon(), app)
    tray.setToolTip(f"{APP_NAME} – {TAGLINE}\nRunning")
    menu = dark_menu()
    title = menu.addAction(f"{APP_NAME} is running")
    title.setEnabled(False)
    menu.addSeparator()
    menu.addAction("Open notch", lambda: window.open(settings.get("default_tab")))
    toggle = menu.addAction("Hide notch")
    toggle.triggered.connect(lambda: window.set_user_hidden(not window.user_hidden))
    menu.aboutToShow.connect(lambda: toggle.setText("Show notch" if window.user_hidden else "Hide notch"))
    menu.addAction("Settings…", open_settings)
    menu.addSeparator()
    menu.addAction("Restart", restart)
    menu.addAction(f"Quit {APP_NAME}", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: open_settings() if reason == QSystemTrayIcon.DoubleClick
                           else window.open(settings.get("default_tab")) if reason == QSystemTrayIcon.Trigger
                           else None)
    tray.show()

    first_run = QSettings(STORAGE_NAME, STORAGE_NAME)
    if not first_run.value("welcomed", False, type=bool):
        first_run.setValue("welcomed", True)
        tray.showMessage(f"{APP_NAME} is running",
                         f"{TAGLINE}. It lives at the top of your screen. Right-click this icon for settings.",
                         app_icon(), 6000)

    if args.settings:
        open_settings()
    log.info("%s started", APP_NAME)
    code = app.exec()
    for service in services:
        service.stop()
    lyrics.shutdown()
    tray.hide()
    if code == RESTART_CODE:
        lock.unlock()
        program, arguments = _restart_command()
        QProcess.startDetached(program, arguments)
        return 0
    return code
