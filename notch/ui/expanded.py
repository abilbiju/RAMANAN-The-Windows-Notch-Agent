"""The expanded notch: Now Playing, File Shelf and Mirror tabs."""

import json
import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QFileInfo, QMimeData, QPoint, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QFileIconProvider, QHBoxLayout,
                               QListWidget, QListWidgetItem, QMenu, QStackedWidget, QVBoxLayout,
                               QWidget)

from ..services.audio import output_devices, set_output_device
from ..services.lyrics import line_at
from ..services.media import current_position
from .theme import FG, MENU_STYLE, SUB, G, text_font
from .widgets import AlbumArt, Bar, GlyphButton, IconSlot, PrivacyDots, TextLabel, Visualizer

log = logging.getLogger(__name__)

# Not %APPDATA%: the Microsoft Store build of Python silently redirects writes
# there into a private package folder, which makes the files hard to find.
DATA_DIR = Path.home() / ".winnotch"
IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "ico"}


def dark_menu(parent=None):
    menu = QMenu(parent)
    menu.setStyleSheet(MENU_STYLE)
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


def fmt_time(seconds):
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def show_in_folder(path):
    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


class MediaPage(QWidget):
    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.snap = {"active": False}
        self.lyrics = None
        self.accent = FG

        root = QHBoxLayout(self)
        root.setContentsMargins(2, 0, 2, 0)
        root.setSpacing(14)
        self.art = AlbumArt(96, 14)
        root.addWidget(self.art, 0, Qt.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(2)
        top = QHBoxLayout()
        names = QVBoxLayout()
        names.setSpacing(0)
        self.title = TextLabel(15, QFont.Weight.DemiBold)
        self.artist = TextLabel(12, color=SUB)
        names.addWidget(self.title)
        names.addWidget(self.artist)
        top.addLayout(names, 1)
        self.viz = Visualizer(5, 3, 3, win.level_source)
        top.addWidget(self.viz, 0, Qt.AlignVCenter)
        col.addLayout(top)
        self.lyric = TextLabel(12, QFont.Weight.Medium)
        col.addWidget(self.lyric)
        col.addStretch()

        progress = QHBoxLayout()
        progress.setSpacing(8)
        self.elapsed = TextLabel(10, color=SUB, align=Qt.AlignRight)
        self.elapsed.setFixedWidth(34)
        self.bar = Bar(4, seekable=True)
        self.bar.seek.connect(self._seek_fraction)
        self.total = TextLabel(10, color=SUB)
        self.total.setFixedWidth(34)
        progress.addWidget(self.elapsed)
        progress.addWidget(self.bar, 1)
        progress.addWidget(self.total)
        col.addLayout(progress)

        controls = QHBoxLayout()
        controls.setSpacing(2)
        self.back = GlyphButton(G.REWIND, 30, 12, "Back 15 seconds")
        self.prev = GlyphButton(G.PREV, 30, 14, "Previous")
        self.play = GlyphButton(G.PLAY, 36, 19, "Play / Pause")
        self.next = GlyphButton(G.NEXT, 30, 14, "Next")
        self.fwd = GlyphButton(G.FORWARD, 30, 12, "Forward 15 seconds")
        self.device = GlyphButton(G.SPEAKER, 30, 13, "Output device")
        self.back.clicked.connect(lambda: self._skip(-15))
        self.fwd.clicked.connect(lambda: self._skip(15))
        self.prev.clicked.connect(lambda: win.media_command("prev"))
        self.next.clicked.connect(lambda: win.media_command("next"))
        self.play.clicked.connect(lambda: win.media_command("toggle"))
        self.device.clicked.connect(self._device_menu)
        spacer = QWidget()
        spacer.setFixedWidth(30)
        controls.addWidget(spacer)
        controls.addStretch()
        for b in (self.back, self.prev, self.play, self.next, self.fwd):
            controls.addWidget(b)
        controls.addStretch()
        controls.addWidget(self.device)
        col.addLayout(controls)
        root.addLayout(col, 1)

        self._timer = QTimer(self, interval=250, timeout=self._tick)
        self.setMedia({"active": False}, None, FG)

    def showEvent(self, _):
        self._timer.start()
        self._tick()

    def hideEvent(self, _):
        self._timer.stop()

    def setMedia(self, snap, image, accent):
        if snap.get("key") != self.snap.get("key"):
            self.lyrics = None
        self.snap = snap
        self.accent = accent
        active = snap.get("active", False)
        self.art.setImage(image)
        self.viz.setColor(accent)
        self.bar.setColor(accent)
        self.lyric.setColor(accent)
        if active:
            self.title.setText(snap.get("title") or "Unknown title")
        else:
            self.title.setText("Nothing playing")
        if active:
            self.artist.setText(" · ".join(x for x in (snap.get("artist"), snap.get("app")) if x))
        else:
            self.artist.setText("Play something in Spotify, a browser or Media Player")
        self.play.setGlyph(G.PAUSE if snap.get("playing") else G.PLAY)
        for b in (self.play, self.back, self.fwd, self.bar):
            b.setEnabled(active)
        self.prev.setEnabled(active and snap.get("can_prev", False))
        self.next.setEnabled(active and snap.get("can_next", False))
        seekable = active and snap.get("can_seek", False) and snap.get("duration", 0) > 0
        self.back.setEnabled(seekable)
        self.fwd.setEnabled(seekable)
        self.bar.seekable = seekable
        self._tick()

    def setLyrics(self, lines):
        self.lyrics = lines
        self._tick()

    def _tick(self):
        snap = self.snap
        if not snap.get("active"):
            self.bar.setValue(0)
            self.elapsed.setText("")
            self.total.setText("")
            self.lyric.setText("")
            return
        pos, dur = current_position(snap), snap.get("duration", 0)
        self.bar.setValue(pos / dur if dur > 0 else 0)
        self.elapsed.setText(fmt_time(pos) if dur > 0 or snap.get("elapsed_only") else "")
        self.total.setText(fmt_time(dur) if dur > 0 else "")
        if self.lyrics:
            self.lyric.setColor(self.accent)
            self.lyric.setText(line_at(self.lyrics, pos + 0.3) or "♪")
        else:
            self.lyric.setColor(SUB)
            self.lyric.setText(snap.get("album", ""))

    def _skip(self, delta):
        self.win.media_command("seek", current_position(self.snap) + delta)

    def _seek_fraction(self, fraction):
        dur = self.snap.get("duration", 0)
        if dur > 0:
            self.win.media_command("seek", fraction * dur)

    def _device_menu(self):
        menu = dark_menu(self)
        try:
            devices = output_devices()
        except Exception:
            log.exception("listing output devices failed")
            devices = []
        for dev_id, name, is_default in devices:
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(is_default)
            act.triggered.connect(lambda _=False, d=dev_id: self._set_device(d))
        if not devices:
            menu.addAction("No playback devices").setEnabled(False)
        self.win.popup(menu, self.device.mapToGlobal(QPoint(0, self.device.height() + 4)))

    def _set_device(self, dev_id):
        try:
            set_output_device(dev_id)
        except Exception:
            log.exception("switching output device failed")


class ShelfList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setMovement(QListWidget.Static)
        self.setIconSize(QSize(36, 36))
        self.setGridSize(QSize(80, 70))
        self.setTextElideMode(Qt.ElideMiddle)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setFrameShape(QListWidget.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QListWidget { background: transparent; color: #f5f5f7; font: 11px 'Segoe UI'; outline: 0; }
            QListWidget::item { border-radius: 10px; padding: 4px; }
            QListWidget::item:hover { background: rgba(255,255,255,0.08); }
            QListWidget::item:selected { background: rgba(10,132,255,0.35); color: #fff; }
            QScrollBar:horizontal { height: 4px; background: transparent; }
            QScrollBar::handle:horizontal { background: rgba(255,255,255,0.25); border-radius: 2px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; }""")

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, items):
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(i.data(Qt.UserRole)) for i in items])
        return data

    def wheelEvent(self, e):
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - e.angleDelta().y())


class ShelfPage(QWidget):
    """Temporary holding area: drop files on the notch, drag them out later."""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.store = DATA_DIR / "shelf.json"
        self.highlight = False
        self._icons = QFileIconProvider()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.list = ShelfList()
        self.list.itemDoubleClicked.connect(lambda item: os.startfile(item.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._item_menu)
        lay.addWidget(self.list, 1)

        footer = QHBoxLayout()
        self.count = TextLabel(11, color=SUB)
        footer.addWidget(self.count, 1)
        clear = GlyphButton(G.DELETE, 26, 12, "Clear shelf")
        clear.clicked.connect(self.clear)
        footer.addWidget(clear)
        lay.addLayout(footer)
        self._load()

    def paths(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def add(self, paths):
        existing = set(self.paths())
        for path in paths:
            path = os.path.normpath(path)
            if path in existing or not os.path.exists(path):
                continue
            existing.add(path)
            item = QListWidgetItem(self._icon(path), Path(path).name or path)
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)
        self._changed()

    def clear(self):
        self.list.clear()
        self._changed()

    def setHighlight(self, on):
        self.highlight = on
        self.update()

    def showEvent(self, _):
        # Drop references to files that were moved or deleted meanwhile.
        for i in reversed(range(self.list.count())):
            if not os.path.exists(self.list.item(i).data(Qt.UserRole)):
                self.list.takeItem(i)
        self._changed()

    def _icon(self, path):
        if Path(path).suffix.lower().lstrip(".") in IMAGE_SUFFIXES:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(QSize(88, 88), Qt.KeepAspectRatio))
            image = reader.read()
            if not image.isNull():
                return QIcon(QPixmap.fromImage(image))
        return self._icons.icon(QFileInfo(path))

    def _item_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        menu = dark_menu(self)
        menu.addAction("Open", lambda: os.startfile(path))
        menu.addAction("Show in folder", lambda: show_in_folder(path))
        menu.addAction("Copy path", lambda: QGuiApplication.clipboard().setText(path))
        menu.addSeparator()
        menu.addAction("Remove from shelf", lambda: (self.list.takeItem(self.list.row(item)), self._changed()))
        self.win.popup(menu, self.list.viewport().mapToGlobal(pos))

    def _changed(self):
        n = self.list.count()
        self.count.setText(f"{n} item{'s' if n != 1 else ''} · drag out to use, double-click to open" if n else "")
        self.update()
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.store.write_text(json.dumps(self.paths(), indent=1), encoding="utf-8")
        except OSError:
            log.exception("saving shelf failed")

    def _load(self):
        try:
            self.add(json.loads(self.store.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def paintEvent(self, _):
        if self.list.count() and not self.highlight:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -24 if self.list.count() else -2)
        pen = QPen(FG if self.highlight else SUB, 1.4, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, 16, 16)
        if not self.list.count():
            p.setFont(text_font(13))
            p.drawText(rect, Qt.AlignCenter, "Drop files here to keep them handy")


class MirrorPage(QWidget):
    """Quick webcam check before a call. The camera only runs while this
    tab is visible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.message = "Starting camera…"
        self.camera = None

    def showEvent(self, _):
        self._start()

    def hideEvent(self, _):
        self._stop()

    def _start(self):
        from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
        if self.camera is not None:
            return
        device = QMediaDevices.defaultVideoInput()
        if device.isNull():
            self.message = "No camera found"
            self.update()
            return
        self.message = "Starting camera…"
        self.camera = QCamera(device)
        self.camera.errorOccurred.connect(self._error)
        self.session = QMediaCaptureSession()
        self.sink = QVideoSink()
        self.session.setCamera(self.camera)
        self.session.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._frame)
        self.camera.start()

    def _stop(self):
        if self.camera is not None:
            self.sink.videoFrameChanged.disconnect(self._frame)
            self.camera.stop()
            self.camera.deleteLater()
            self.camera = None
        self.image = None

    def _error(self, _error, text):
        self.message = text or "Camera unavailable"
        self._stop()
        self.update()

    def _frame(self, frame):
        image = frame.toImage()
        if not image.isNull():
            self.image = image
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        h = self.height()
        w = min(self.width(), h * 16 / 9)
        view = QRectF((self.width() - w) / 2, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(view, 18, 18)
        p.setClipPath(path)
        p.fillRect(view, QColor(28, 28, 30))
        if self.image is None:
            p.setPen(SUB)
            p.setFont(text_font(13))
            p.drawText(view, Qt.AlignCenter, self.message)
            return
        img = self.image
        scale = max(view.width() / img.width(), view.height() / img.height())
        tw, th = img.width() * scale, img.height() * scale
        p.translate(view.center().x(), view.center().y())
        p.scale(-1, 1)  # mirror, like looking into a real mirror
        p.drawImage(QRectF(-tw / 2, -th / 2, tw, th), img)


class ExpandedView(QWidget):
    TABS = ((G.HOME, "Now playing"), (G.FOLDER, "File shelf"), (G.CAMERA, "Mirror"))

    def __init__(self, win, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 2, 14, 10)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(2)
        self.group = QButtonGroup(self)
        for i, (glyph, tip) in enumerate(self.TABS):
            b = GlyphButton(glyph, 26, 12, tip)
            b.setCheckable(True)
            self.group.addButton(b, i)
            header.addWidget(b)
        header.addStretch()
        self.dots = PrivacyDots()
        header.addWidget(self.dots)
        header.addSpacing(8)
        self.battery_text = TextLabel(12, color=SUB, align=Qt.AlignRight)
        self.battery_text.setFixedWidth(40)
        self.battery_icon = IconSlot()
        self.battery_text.hide()
        self.battery_icon.hide()
        header.addWidget(self.battery_text)
        header.addWidget(self.battery_icon)
        settings = GlyphButton(G.SETTINGS, 26, 12, "Settings")
        settings.clicked.connect(lambda: win.settings_menu(settings.mapToGlobal(QPoint(0, settings.height() + 4))))
        header.addWidget(settings)
        lay.addLayout(header)

        self.stack = QStackedWidget()
        self.media = MediaPage(win)
        self.shelf = ShelfPage(win)
        self.mirror = MirrorPage()
        for page in (self.media, self.shelf, self.mirror):
            self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)
        self.group.idClicked.connect(self.showTab)
        self.showTab(0)

    def showTab(self, index):
        if not self.group.button(index).isVisibleTo(self):
            index = 0
        self.group.button(index).setChecked(True)
        self.stack.setCurrentIndex(index)

    def setMirrorEnabled(self, enabled):
        self.group.button(2).setVisible(enabled)
        if not enabled and self.stack.currentIndex() == 2:
            self.showTab(0)

    def setBattery(self, percent, plugged):
        self.battery_text.setText(f"{percent}%")
        self.battery_icon.setSpec(("battery", percent, plugged))
        self.battery_text.show()
        self.battery_icon.show()
