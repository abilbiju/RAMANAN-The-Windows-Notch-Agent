"""Customisation window. Every control writes straight to Settings, and the
notch reacts to Settings.changed, so changes apply live."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSlider, QTabWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, REPO, VERSION
from ..settings import DEFAULTS, autostart_enabled, set_autostart

STYLE = """
QWidget { background: #1c1c1e; color: #f5f5f7; font: 13px 'Segoe UI'; }
QTabWidget::pane { border: 1px solid #3a3a3c; border-radius: 10px; top: -1px; }
QTabBar::tab { background: transparent; color: #98989d; padding: 8px 16px; border: none; }
QTabBar::tab:selected { color: #f5f5f7; border-bottom: 2px solid #0a84ff; }
QLabel#hint { color: #98989d; font-size: 12px; }
QLabel#section { color: #98989d; font-size: 11px; font-weight: 600; padding-top: 6px; }
QComboBox, QPushButton { background: #2c2c2e; border: 1px solid #3a3a3c; border-radius: 7px;
                         padding: 5px 10px; min-height: 18px; }
QPushButton:hover, QComboBox:hover { background: #3a3a3c; }
QPushButton#primary { background: #0a84ff; border-color: #0a84ff; }
QComboBox QAbstractItemView { background: #2c2c2e; selection-background-color: #0a84ff; border: 1px solid #3a3a3c; }
QCheckBox { spacing: 10px; padding: 3px 0; }
QCheckBox::indicator { width: 34px; height: 20px; image: url(%TOGGLE_OFF%); }
QCheckBox::indicator:checked { image: url(%TOGGLE_ON%); }
QSlider::groove:horizontal { height: 4px; background: #3a3a3c; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #0a84ff; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: #f5f5f7; }
QFrame#banner { background: #0a3d1f; border: 1px solid #30d158; border-radius: 10px; }
QFrame#banner QLabel { background: transparent; }
"""

UPDATE_STATUS = {"checking": "Checking for updates…", "latest": "You're on the latest version.",
                 "error": "Couldn't reach GitHub. Will try again later."}


class SettingsWindow(QWidget):
    restart_requested = Signal()
    preview_requested = Signal()
    check_requested = Signal()

    def __init__(self, settings):
        super().__init__(None, Qt.Window)
        self.settings = settings
        self.setWindowTitle(f"{APP_NAME} Settings")
        assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])) / "assets"
        self.setStyleSheet(STYLE.replace("%TOGGLE_OFF%", (assets / "toggle_off.svg").as_posix())
                                .replace("%TOGGLE_ON%", (assets / "toggle_on.svg").as_posix()))
        self.resize(560, 600)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        self.tabs = tabs = QTabWidget()
        tabs.addTab(self._appearance(), "Appearance")
        tabs.addTab(self._behaviour(), "Behaviour")
        tabs.addTab(self._notifications(), "Notifications")
        self._about_index = tabs.addTab(self._about(), "About")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset)
        preview = QPushButton("Preview a HUD")
        preview.clicked.connect(self.preview_requested)
        close = QPushButton("Done")
        close.setObjectName("primary")
        close.clicked.connect(self.close)
        footer.addWidget(reset)
        footer.addStretch()
        footer.addWidget(preview)
        footer.addWidget(close)
        root.addLayout(footer)

    # ---- bound controls --------------------------------------------------------

    def _check(self, key, label):
        box = QCheckBox(label)
        box.setChecked(self.settings.get(key))
        box.toggled.connect(lambda on: self.settings.set(key, on))
        self.settings.changed.connect(lambda k: k == key and box.setChecked(self.settings.get(key)))
        return box

    def _combo(self, key, options):
        combo = QComboBox()
        for label, value in options:
            combo.addItem(label, value)

        def sync(k=key):
            if k == key:
                i = combo.findData(self.settings.get(key))
                combo.setCurrentIndex(max(i, 0))
        sync()
        combo.currentIndexChanged.connect(lambda _: self.settings.set(key, combo.currentData()))
        self.settings.changed.connect(sync)
        return combo

    def _slider(self, key, lo, hi, fmt, factor=1):
        """Integer slider; the stored value is slider position / factor."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(lo, hi)
        label = QLabel()
        label.setFixedWidth(56)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(slider, 1)
        lay.addWidget(label)
        cast = type(DEFAULTS[key])

        def sync(k=key):
            if k == key:
                slider.blockSignals(True)
                slider.setValue(round(self.settings.get(key) * factor))
                slider.blockSignals(False)
                label.setText(fmt(self.settings.get(key)))

        def moved(v):
            self.settings.set(key, cast(v / factor))
            label.setText(fmt(cast(v / factor)))
        slider.valueChanged.connect(moved)
        self.settings.changed.connect(sync)
        sync()
        return row

    def _page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(18)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return page, form

    @staticmethod
    def _section(form, text):
        label = QLabel(text.upper())
        label.setObjectName("section")
        form.addRow(label)

    @staticmethod
    def _hint(text):
        label = QLabel(text)
        label.setObjectName("hint")
        label.setWordWrap(True)
        return label

    # ---- pages ----------------------------------------------------------------

    def _appearance(self):
        page, form = self._page()
        self._section(form, "Notch")
        form.addRow("Resting style", self._combo("idle_style", [
            ("Pill", "pill"), ("Slim bar", "slim"), ("Invisible (hover to reveal)", "invisible")]))
        form.addRow("Resting width", self._slider("idle_width", 100, 320, lambda v: f"{v} px"))
        form.addRow("Size", self._combo("scale", [
            ("Small (85%)", 0.85), ("Normal (100%)", 1.0), ("Large (115%)", 1.15), ("Extra large (130%)", 1.3)]))
        restart = QPushButton("Restart to apply size")
        restart.clicked.connect(self.restart_requested)
        form.addRow("", restart)
        screens = [("Primary display", "")] + [(s.name(), s.name()) for s in QGuiApplication.screens()]
        form.addRow("Display", self._combo("display", screens))

        self._section(form, "Colour")
        form.addRow("Accent colour", self._combo("accent_mode", [
            ("Match album artwork", "artwork"), ("Custom colour", "custom")]))
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self._pick_color)
        self._paint_color_button()
        self.settings.changed.connect(lambda k: k == "accent_color" and self._paint_color_button())
        form.addRow("Custom colour", self.color_button)
        form.addRow("", self._check("visualizer", "Show audio visualizer bars"))

        self._section(form, "Mascot")
        form.addRow("Character", self._combo("mascot", [
            ("Ramanan (pixel art)", "ramanan"), ("None", "none")]))
        form.addRow(self._hint("Ramanan stands in the resting notch with fish swimming past, and dances "
                               "in the now-playing pill when music plays. He naps when you're away, sweats "
                               "on low battery, parties when a download finishes and gasps when the camera "
                               "turns on. Shown with the Pill resting style."))
        return page

    def _behaviour(self):
        page, form = self._page()
        self._section(form, "General")
        startup = QCheckBox(f"Start {APP_NAME} when I sign in to Windows")
        startup.setChecked(autostart_enabled())
        startup.toggled.connect(set_autostart)
        form.addRow(startup)
        form.addRow(self._check("hide_fullscreen", "Hide in fullscreen games, videos and slideshows"))

        self._section(form, "Position")
        form.addRow(self._hint("Drag the notch to any screen edge to dock it there, or drop it in the "
                               "middle of the screen to make it a floating pill."))
        form.addRow(self._check("lock_position", "Lock position (disable dragging)"))
        home = QPushButton("Move back to top centre")
        home.clicked.connect(lambda: (self.settings.set("dock_edge", "top"),
                                      self.settings.set("dock_pos", 0.5)))
        form.addRow("", home)

        self._section(form, "Interaction")
        form.addRow("Hover delay", self._slider("hover_delay", 0, 600, lambda v: f"{v} ms"))
        form.addRow("HUD duration", self._slider("hud_duration", 5, 30, lambda v: f"{v:.1f}×", 10))
        form.addRow("Opens on", self._combo("default_tab", [
            ("Now playing", 0), ("File shelf", 1), ("Mirror", 2)]))
        form.addRow(self._check("show_mirror", "Show the Mirror (webcam) tab"))

        self._section(form, "Media")
        form.addRow(self._check("compact_media", "Show the now-playing pill while music plays"))
        form.addRow(self._check("hud_track", "Announce track changes"))
        form.addRow(self._check("lyrics", "Show synced lyrics"))
        form.addRow(self._hint("Lyrics are looked up on lrclib.net using the track title, artist and album. "
                               "When a song changes on its own in a browser player, its length may stay "
                               "hidden until you seek or skip."))
        return page

    def _notifications(self):
        page, form = self._page()
        self._section(form, "Show a HUD for")
        for key, label in (("hud_volume", "Volume"), ("hud_brightness", "Screen brightness"),
                           ("hud_locks", "Caps Lock and Num Lock"), ("hud_focus", "Do Not Disturb"),
                           ("hud_battery", "Charging, unplugging and low battery"),
                           ("hud_privacy", "Camera and microphone use"),
                           ("hud_downloads", "Download progress and completion")):
            form.addRow(self._check(key, label))
        form.addRow(self._hint("Camera and microphone dots stay visible even when the HUD is turned off."))
        return page

    def _about(self):
        page, form = self._page()
        self._section(form, APP_NAME)
        form.addRow("Version", QLabel(f"v{VERSION}"))

        self.banner = QFrame()
        self.banner.setObjectName("banner")
        lay = QVBoxLayout(self.banner)
        lay.setContentsMargins(14, 12, 14, 12)
        self.banner_title = QLabel()
        self.banner_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.banner_notes = self._hint("")
        buttons = QHBoxLayout()
        self.download_button = QPushButton("Download")
        self.download_button.setObjectName("primary")
        notes = QPushButton("What's new")
        buttons.addWidget(self.download_button)
        buttons.addWidget(notes)
        buttons.addStretch()
        lay.addWidget(self.banner_title)
        lay.addWidget(self.banner_notes)
        lay.addLayout(buttons)
        self.download_button.clicked.connect(lambda: self._open(self._update.get("download") or self._update["page"]))
        notes.clicked.connect(lambda: self._open(self._update["page"]))
        self.banner.hide()
        self._update = {}
        form.addRow(self.banner)

        self._section(form, "Updates")
        form.addRow(self._check("check_updates", "Check for new versions automatically"))
        row = QHBoxLayout()
        row.setSpacing(12)
        check = QPushButton("Check now")
        check.clicked.connect(self.check_requested)
        self.update_status = self._hint("")
        row.addWidget(check)
        row.addWidget(self.update_status, 1)
        form.addRow(row)
        form.addRow(self._hint(f"Asks GitHub for the latest release of {REPO}. Download the new "
                               f"Ramanan.exe and replace the old one to update."))
        return page

    def show_update(self, info):
        state = info["state"]
        if state == "available":
            self._update = info
            self.banner_title.setText(f"{APP_NAME} v{info['version']} is available")
            first = next((l.strip("-*# ").strip() for l in info["notes"].splitlines() if l.strip()), "")
            self.banner_notes.setText(first or f"You have v{VERSION}.")
            self.banner.show()
            self.update_status.setText(f"v{info['version']} is ready to download.")
            self.tabs.setTabText(self._about_index, "About  ●")
        else:
            self.update_status.setText(UPDATE_STATUS[state])
            if state == "latest":
                self.banner.hide()
                self.tabs.setTabText(self._about_index, "About")

    @staticmethod
    def _open(url):
        QDesktopServices.openUrl(QUrl(url))

    # ---- helpers --------------------------------------------------------------

    def _paint_color_button(self):
        color = self.settings.get("accent_color")
        self.color_button.setText(color.upper())
        text = "#000" if QColor(color).lightnessF() > 0.6 else "#fff"
        self.color_button.setStyleSheet(f"background: {color}; color: {text}; border-color: {color};")

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.settings.get("accent_color")), self, "Accent colour")
        if color.isValid():
            self.settings.set("accent_color", color.name())
            self.settings.set("accent_mode", "custom")

    def _reset(self):
        self.settings.reset()

    def closeEvent(self, e):
        # The app keeps running in the tray; just hide the window.
        e.ignore()
        self.hide()
