"""The notch window: shape + spring animation, the state machine that picks
what to show, and the mapping from system events to HUDs."""

import ctypes
import logging
import os
import time

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPainterPath, QTransform
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget

from .. import APP_NAME
from .expanded import DATA_DIR, ExpandedView, dark_menu, show_in_folder
from .mascot import Mood
from .theme import BG, BLUE, FG, GREEN, ORANGE, PURPLE, RED, SUB, YELLOW, G
from .views import CompactView, HudView, IdleView
from .widgets import accent_from_image

log = logging.getLogger(__name__)

# content width, height, bottom corner radius for each state
SIZES = {
    "idle": (180, 28, 14),
    "compact": (300, 34, 17),
    "hud": (370, 56, 22),
    "activity": (380, 56, 22),
    "expanded": (520, 170, 26),
}
EAR = 10       # concave flare where the notch meets the screen edge
SPRING_ROOM = 24  # spare window space so the overshoot isn't clipped
SNAP_DISTANCE = 70  # release this close to a screen edge to dock there
DRAG_THRESHOLD = 6


def _clamp(value, lo, hi):
    return max(lo, min(value, hi))


def notch_path(length, depth, radius, ear):
    """Notch outline in 'edge space': the flat side lies on the screen edge
    along y = 0, `length` runs along the edge (ears included) and `depth`
    sticks out into the screen. Transformed per edge when painting."""
    r = max(1.0, min(radius, depth / 2, (length - 2 * ear) / 2))
    path = QPainterPath()
    path.moveTo(0, 0)
    path.quadTo(ear, 0, ear, min(ear, depth - r))
    path.lineTo(ear, depth - r)
    path.arcTo(QRectF(ear, depth - 2 * r, 2 * r, 2 * r), 180, 90)
    path.lineTo(length - ear - r, depth)
    path.arcTo(QRectF(length - ear - 2 * r, depth - 2 * r, 2 * r, 2 * r), 270, 90)
    path.lineTo(length - ear, min(ear, depth - r))
    path.quadTo(length - ear, 0, length, 0)
    path.closeSubpath()
    return path


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class Surface(QWidget):
    """The black notch shape. Forwards hover, clicks, drags and file drops."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.radius = 14
        self._press = None
        self._dragging = False
        self._track = QTimer(self, interval=16, timeout=self._track_tick)
        self.setAcceptDrops(True)

    def _path(self):
        w, h, edge = self.width(), self.height(), self.win.edge
        if edge == "float":
            path = QPainterPath()
            r = min(self.radius, w / 2, h / 2)
            path.addRoundedRect(QRectF(0, 0, w, h), r, r)
            return path
        if edge in ("top", "bottom"):
            path = notch_path(w, h, self.radius, EAR)
            return path if edge == "top" else QTransform(1, 0, 0, -1, 0, h).map(path)
        path = notch_path(h, w, self.radius, EAR)
        # swap axes so the flat side lies on the left / right screen edge
        return QTransform(0, 1, 1, 0, 0, 0).map(path) if edge == "left" else \
            QTransform(0, 1, -1, 0, w, 0).map(path)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Alpha 1 is invisible but still receives the mouse, so an
        # "invisible" resting notch can still be hovered open.
        invisible = self.win.mode == "idle" and self.win.idle_style() == "invisible"
        p.fillPath(self._path(), QColor(0, 0, 0, 1) if invisible else BG)

    def enterEvent(self, _):
        self.win.hover_enter()

    def leaveEvent(self, _):
        self.win.hover_leave()

    def mousePressEvent(self, e):
        # The drag is tracked by polling the cursor rather than through Qt's
        # move/release events: starting a drag collapses the notch and hides
        # the widget that was clicked, which would cut off Qt's event stream.
        if e.button() == Qt.LeftButton and self._press is None:
            self._press = QCursor.pos()
            self._dragging = False
            self._track.start()

    def _track_tick(self):
        user32 = ctypes.windll.user32
        button = 0x02 if user32.GetSystemMetrics(23) else 0x01  # SM_SWAPBUTTON
        pos = QCursor.pos()
        if user32.GetAsyncKeyState(button) & 0x8000:
            if not self._dragging and (pos - self._press).manhattanLength() > DRAG_THRESHOLD \
                    and not self.win.settings.get("lock_position"):
                self._dragging = True
                self.win.begin_drag()
            if self._dragging:
                self.win.drag_to(pos)
            return
        self._track.stop()
        if self._dragging:
            self.win.end_drag()
        else:
            self.win.clicked()
        self._press = None
        self._dragging = False

    def contextMenuEvent(self, e):
        self.win.settings_menu(e.globalPos())

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.win.drag_enter()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, _):
        self.win.drag_leave()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        e.acceptProposedAction()
        self.win.drop(paths)


class NotchWindow(QWidget):
    def __init__(self, bus, media, audio, lyrics, settings):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        max_w, max_h, _ = SIZES["expanded"]
        # Room for the expanded panel in any orientation; the transparent
        # parts of the window are click-through.
        self.resize(max_w + 2 * EAR + 2 * SPRING_ROOM, max_h + 2 * EAR + 2 * SPRING_ROOM)

        self.media_service = media
        self.audio = audio
        self.lyrics = lyrics
        self.settings = settings
        self._load_position()
        self.window_dragging = False
        self._anchor = (0.0, 0.0)  # where the resting notch sits, in window coordinates
        self._t = 1.0

        self.media = {"active": False}
        self.media_image = None
        self.accent = FG
        self._art = b""
        self.battery = None
        self.privacy = None
        self.downloads = []
        self.fullscreen = False
        self.expanded = False
        self.dragging = False
        self.holds = 0
        self.hud_on = False
        self.hud_action = None
        self.user_hidden = False
        self.open_settings = None  # set by the app
        self._outside_since = None

        self.surface = Surface(self)
        self.mood = Mood(bus)
        self.idle_view = IdleView(self.level_source, self.mood, self.surface)
        self.compact_view = CompactView(self.level_source, self.mood, self.surface)
        self.hud_view = HudView(self.surface)
        self.activity_view = HudView(self.surface)
        self.expanded_view = ExpandedView(self, self.surface)
        self.views = {"idle": self.idle_view, "compact": self.compact_view, "hud": self.hud_view,
                      "activity": self.activity_view, "expanded": self.expanded_view}
        for view in self.views.values():
            view.hide()

        self.mode = None
        self.geom = self._size("idle")
        self._from = self._to = self.geom
        self._content_shown = False
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0)
        self._anim.valueChanged.connect(self._step)

        self._expand_timer = QTimer(self, singleShot=True, timeout=self._hover_expand)
        self._hud_timer = QTimer(self, singleShot=True, timeout=self._hud_done)
        self._linger = QTimer(self, singleShot=True, interval=4000, timeout=self._resolve)
        self._watch = QTimer(self, interval=120, timeout=self._watch_cursor)

        bus.media.connect(self.on_media)
        bus.lyrics.connect(self.on_lyrics)
        bus.volume.connect(self.on_volume)
        bus.brightness.connect(self.on_brightness)
        bus.lock_key.connect(self.on_lock_key)
        bus.focus.connect(self.on_focus)
        bus.battery.connect(self.on_battery)
        bus.privacy.connect(self.on_privacy)
        bus.downloads.connect(self.on_downloads)
        bus.download_done.connect(self.on_download_done)
        bus.fullscreen.connect(self.on_fullscreen)

        app = QApplication.instance()
        for screen in app.screens():
            screen.geometryChanged.connect(self.place)
        app.screenAdded.connect(lambda s: (s.geometryChanged.connect(self.place), self.place()))
        app.screenRemoved.connect(lambda _: QTimer.singleShot(0, self.place))
        app.primaryScreenChanged.connect(lambda _: self.place())
        settings.changed.connect(self.on_setting)
        for key in ("hover_delay", "visualizer", "show_mirror", "accent_mode", "mascot"):
            self.on_setting(key)
        self.place()
        self._set_mode("idle", instant=True)

    # ---- settings -------------------------------------------------------------

    def on_setting(self, key):
        s = self.settings
        if key == "hover_delay":
            self._expand_timer.setInterval(s.get("hover_delay"))
        elif key == "visualizer":
            on = s.get("visualizer")
            self.compact_view.viz.setVisible(on)
            self.expanded_view.media.viz.setVisible(on)
        elif key == "show_mirror":
            self.expanded_view.setMirrorEnabled(s.get("show_mirror"))
        elif key in ("accent_mode", "accent_color"):
            self._refresh_accent()
        elif key in ("idle_style", "idle_width", "mascot"):
            self._apply_idle_style()
            if self.mode in ("idle", "compact"):
                self._reshape()
        elif key in ("display", "dock_edge", "dock_pos", "float_x", "float_y"):
            if not self.window_dragging:  # dragging saves these itself
                edge = self.edge
                self._load_position()
                self.place()
                if edge != self.edge:
                    self._apply_idle_style()
                    self._reshape()
        elif key == "lyrics":
            if s.get("lyrics") and self.media.get("active"):
                self.lyrics.fetch(self.media)
            elif not s.get("lyrics"):
                self.expanded_view.media.setLyrics(None)
        elif key == "hide_fullscreen":
            self._apply_visibility()
        elif key == "compact_media":
            self._resolve()

    def _apply_idle_style(self):
        pill = self.idle_style() == "pill"
        self.idle_view.setVisible(self.mode == "idle" and pill)
        self.idle_view.dots.setVisible(pill and self.edge != "float")
        self.idle_view.setMascot(self._mascot() and pill)
        self.compact_view.setMascot(self._mascot())

    def _refresh_accent(self):
        if self.settings.get("accent_mode") == "custom":
            self.accent = QColor(self.settings.get("accent_color"))
        else:
            self.accent = accent_from_image(self.media_image)
        self.compact_view.setMedia(self.media, self.media_image, self.accent)
        self.expanded_view.media.setMedia(self.media, self.media_image, self.accent)

    def _mascot(self):
        return self.settings.get("mascot") != "none"

    def idle_style(self):
        # A floating bubble is always drawn, otherwise it would be lost mid-screen.
        return "pill" if self.edge == "float" else self.settings.get("idle_style")

    def _size(self, mode):
        """(content width, content height, corner radius). On the left/right
        edges width is the depth into the screen, height runs along the edge."""
        mascot = self._mascot()
        # The mascot is 38 px tall, so the resting and now-playing pills grow to fit him.
        if mode == "compact" and mascot:
            return (300, 42, 21 if self.edge == "float" else 18)
        if mode != "idle":
            return SIZES[mode]
        width = self.settings.get("idle_width")
        style = self.idle_style()
        if self.edge == "float":
            # elongated, fully rounded pill
            return (max(width, 170), 44, 22) if mascot else (max(width, 120), 30, 15)
        if self.edge in ("left", "right"):
            if style == "slim":
                return (6, width, 3)
            if style == "invisible":
                return (8, width, 4)
            return (120, 44, 18) if mascot else (28, width, 14)
        if style == "slim":
            return (width, 6, 3)
        if style == "pill" and mascot:
            return (max(width, 170), 42, 18)
        return (width, 28, 14)

    # ---- position: docking & dragging -------------------------------------------

    def _load_position(self):
        s = self.settings
        self.edge = s.get("dock_edge")
        self.dock_pos = s.get("dock_pos")
        self.float_pos = (s.get("float_x"), s.get("float_y"))
        self.screen_name = s.get("display")

    def _save_position(self):
        s = self.settings
        s.set("dock_edge", self.edge)
        s.set("dock_pos", round(self.dock_pos, 4))
        s.set("float_x", round(self.float_pos[0], 4))
        s.set("float_y", round(self.float_pos[1], 4))
        s.set("display", self.screen_name)

    def _screen(self):
        screens = {s.name(): s for s in QApplication.screens()}
        return screens.get(self.screen_name) or QApplication.primaryScreen()

    def place(self):
        screen = self._screen()
        geo, avail = screen.geometry(), screen.availableGeometry()
        W, H = self.width(), self.height()
        edge = self.edge
        if edge in ("top", "bottom"):
            cx = geo.x() + self.dock_pos * geo.width()
            wx = _clamp(cx - W / 2, geo.x(), geo.x() + geo.width() - W)
            wy = geo.y() if edge == "top" else avail.y() + avail.height() - H
            self._anchor = (cx - wx, 0.0)
        elif edge in ("left", "right"):
            cy = geo.y() + self.dock_pos * geo.height()
            wy = _clamp(cy - H / 2, avail.y(), avail.y() + avail.height() - H)
            wx = avail.x() if edge == "left" else avail.x() + avail.width() - W
            self._anchor = (0.0, cy - wy)
        else:
            cx = geo.x() + self.float_pos[0] * geo.width()
            cy = geo.y() + self.float_pos[1] * geo.height()
            wx = _clamp(cx - W / 2, geo.x(), geo.x() + geo.width() - W)
            wy = _clamp(cy - H / 2, geo.y(), geo.y() + geo.height() - H)
            self._anchor = (cx - wx, cy - wy)
        self.move(round(wx), round(wy))
        if self.mode is not None:
            self._step(self._t)

    def _reshape(self):
        """Re-run the current state's animation after the size or edge changed."""
        if self.mode is not None:
            mode, self.mode = self.mode, None
            self._set_mode(mode)

    def begin_drag(self):
        self.window_dragging = True
        self.expanded = False
        self._expand_timer.stop()
        self._resolve()

    def drag_to(self, pos):
        screen = QGuiApplication.screenAt(pos) or self._screen()
        geo = screen.geometry()
        gaps = {"top": pos.y() - geo.y(), "bottom": geo.y() + geo.height() - pos.y(),
                "left": pos.x() - geo.x(), "right": geo.x() + geo.width() - pos.x()}
        nearest = min(gaps, key=gaps.get)
        edge = nearest if gaps[nearest] < SNAP_DISTANCE else "float"
        fx = _clamp((pos.x() - geo.x()) / geo.width(), 0.0, 1.0)
        fy = _clamp((pos.y() - geo.y()) / geo.height(), 0.0, 1.0)
        self.screen_name = screen.name()
        if edge == "float":
            self.float_pos = (fx, fy)
        else:
            self.dock_pos = fx if edge in ("top", "bottom") else fy
        changed = edge != self.edge
        self.edge = edge
        self.place()
        if changed:
            self._apply_idle_style()
            self._reshape()

    def end_drag(self):
        self.window_dragging = False
        self._save_position()
        log.info("notch docked: %s", self.edge)

    def reset_position(self):
        self.settings.set("dock_edge", "top")
        self.settings.set("dock_pos", 0.5)  # on_setting moves the notch

    def _set_mode(self, mode, instant=False):
        if mode == self.mode:
            return
        if self.mode is not None:
            self.views[self.mode].hide()
        self.mode = mode
        self._from, self._to = self.geom, self._size(mode)
        self._content_shown = False
        self._anim.stop()
        if mode == "expanded":
            self._outside_since = None
            self._watch.start()
        else:
            self._watch.stop()
        if instant:
            self._step(1.0)
            return
        grow = self._to[0] * self._to[1] > self._from[0] * self._from[1]
        curve = QEasingCurve(QEasingCurve.OutBack if grow else QEasingCurve.OutCubic)
        if grow:
            curve.setOvershoot(1.1)
        self._anim.setEasingCurve(curve)
        self._anim.setDuration(460 if grow else 320)
        self._anim.start()

    def _outer(self, w, h):
        """Surface size for content w x h: ears run along the docked edge."""
        if self.edge in ("top", "bottom"):
            return w + 2 * EAR, h
        if self.edge in ("left", "right"):
            return w, h + 2 * EAR
        return w, h

    def _step(self, t):
        self._t = t
        a, b = self._from, self._to
        w, h, r = (a[i] + (b[i] - a[i]) * t for i in range(3))
        W, H = self.width(), self.height()
        w = min(w, W - 2 * EAR)
        h = min(h, H - 2 * EAR)
        self.geom = (w, h, r)
        fw, fh = self._outer(w, h)
        ax, ay = self._anchor
        # Centre on the anchor, sliding inward only as far as needed to stay on screen.
        cx = _clamp(ax, fw / 2, W - fw / 2)
        cy = _clamp(ay, fh / 2, H - fh / 2)
        x, y = {"top": (cx - fw / 2, 0), "bottom": (cx - fw / 2, H - fh),
                "left": (0, cy - fh / 2), "right": (W - fw, cy - fh / 2)}.get(
            self.edge, (cx - fw / 2, cy - fh / 2))
        self.surface.setGeometry(round(x), round(y), round(fw), round(fh))
        self.surface.radius = r
        self.surface.update()

        view = self.views[self.mode]
        tw, th, _ = self._to
        vx, vy = {"top": ((fw - tw) / 2, 0), "bottom": ((fw - tw) / 2, fh - th),
                  "left": (0, (fh - th) / 2), "right": (fw - tw, (fh - th) / 2)}.get(
            self.edge, ((fw - tw) / 2, (fh - th) / 2))
        view.setGeometry(round(vx), round(vy), tw, th)
        if t >= 0.55 and not self._content_shown:
            self._content_shown = True
            if self.mode != "idle" or self.idle_style() == "pill":
                self._fade_in(view)

    def _fade_in(self, view):
        effect = QGraphicsOpacityEffect(view)
        effect.setOpacity(0.0)
        view.setGraphicsEffect(effect)
        view.show()
        fade = QPropertyAnimation(effect, b"opacity", view, duration=170, startValue=0.0, endValue=1.0)
        fade.finished.connect(lambda: view.setGraphicsEffect(None))
        fade.start(QPropertyAnimation.DeleteWhenStopped)

    def _resolve(self):
        if self.expanded or self.dragging or self.holds:
            mode = "expanded"
        elif self.hud_on:
            mode = "hud"
        elif self.downloads and self.settings.get("hud_downloads"):
            mode = "activity"
        elif (self.settings.get("compact_media") and self.media.get("active")
              and (self.media.get("playing") or self._linger.isActive())):
            mode = "compact"
        else:
            mode = "idle"
        self._set_mode(mode)

    # ---- interaction ----------------------------------------------------------

    def level_source(self):
        return getattr(self.audio, "level", 0.0), self.media.get("playing", False)

    def media_command(self, name, arg=None):
        self.media_service.command(name, arg)

    def _cursor_inside(self, margin=0):
        rect = QRect(self.surface.mapToGlobal(QPoint(0, 0)), self.surface.size())
        return rect.adjusted(-margin, -margin, margin, margin).contains(QCursor.pos())

    def hover_enter(self):
        if self.mode != "expanded" and not self.window_dragging:
            self._expand_timer.start()

    def hover_leave(self):
        self._expand_timer.stop()

    def _hover_expand(self):
        if self._cursor_inside():
            self.open(self.settings.get("default_tab"))

    def open(self, tab=None):
        if tab is not None:
            self.expanded_view.showTab(tab)
        self.expanded = True
        self._resolve()

    def _watch_cursor(self):
        if self._cursor_inside(6) or self.holds or self.dragging or QApplication.activePopupWidget():
            self._outside_since = None
            return
        now = time.monotonic()
        if self._outside_since is None:
            self._outside_since = now
        elif now - self._outside_since > 0.35:
            self.expanded = False
            self._resolve()

    def clicked(self):
        if self.mode == "hud" and self.hud_action is not None:
            action, self.hud_action = self.hud_action, None
            action()
            self._hud_done()
        elif self.mode != "expanded":
            self.open(self.settings.get("default_tab"))

    def drag_enter(self):
        self.dragging = True
        self.expanded = True
        self.expanded_view.showTab(1)
        self.expanded_view.shelf.setHighlight(True)
        self._resolve()

    def drag_leave(self):
        self.dragging = False
        self.expanded_view.shelf.setHighlight(False)

    def drop(self, paths):
        self.dragging = False
        self.expanded_view.shelf.setHighlight(False)
        self.expanded_view.shelf.add(paths)

    def popup(self, menu, pos):
        self.holds += 1
        try:
            menu.exec(pos)
        finally:
            self.holds -= 1
            self._outside_since = None

    def settings_menu(self, pos):
        menu = dark_menu(self)
        menu.addAction("Settings…", lambda: self.open_settings and self.open_settings())
        act = menu.addAction("Show synced lyrics")
        act.setCheckable(True)
        act.setChecked(self.settings.get("lyrics"))
        act.toggled.connect(lambda on: self.settings.set("lyrics", on))
        act = menu.addAction("Lock position")
        act.setCheckable(True)
        act.setChecked(self.settings.get("lock_position"))
        act.toggled.connect(lambda on: self.settings.set("lock_position", on))
        menu.addAction("Move back to top centre", self.reset_position)
        menu.addSeparator()
        menu.addAction("Hide notch", lambda: self.set_user_hidden(True))
        menu.addAction("Open data folder", lambda: os.startfile(DATA_DIR))
        menu.addAction(f"Quit {APP_NAME}", QApplication.quit)
        self.popup(menu, pos)

    def set_user_hidden(self, hidden):
        self.user_hidden = hidden
        if hidden:
            self.expanded = False
            self._resolve()
        self._apply_visibility()

    def _apply_visibility(self):
        hide = self.user_hidden or (self.fullscreen and self.settings.get("hide_fullscreen"))
        if hide and self.isVisible():
            self.hide()
        elif not hide and not self.isVisible():
            self.show()

    # ---- HUDs -----------------------------------------------------------------

    def show_hud(self, kind, icon, title, subtitle="", bar=None, color=FG, value="", value_color=FG,
                 duration=1700, action=None, animate=False):
        """kind names the settings toggle (hud_<kind>); None always shows."""
        if kind and not self.settings.get(f"hud_{kind}"):
            return
        duration = int(duration * self.settings.get("hud_duration"))
        self.hud_view.setSpec(dict(icon=icon, title=title, subtitle=subtitle, bar=bar, color=color,
                                   value=value, value_color=value_color, animate=animate))
        self.hud_action = action
        self.hud_on = True
        self._hud_timer.start(duration)
        self._resolve()

    def _hud_done(self):
        self.hud_on = False
        self.hud_action = None
        self._resolve()

    # ---- service events -------------------------------------------------------

    def on_media(self, snap):
        prev, self.media = self.media, snap
        art = snap.get("art", b"")
        if art != self._art:
            self._art = art
            image = QImage.fromData(art) if art else None
            self.media_image = image if image is not None and not image.isNull() else None
            if self.settings.get("accent_mode") == "artwork":
                self.accent = accent_from_image(self.media_image)
        if prev.get("playing") and not snap.get("playing"):
            self._linger.start()
        self.compact_view.setMedia(snap, self.media_image, self.accent)
        self.expanded_view.media.setMedia(snap, self.media_image, self.accent)
        if snap.get("active") and snap.get("key") != prev.get("key"):
            if self.settings.get("lyrics") and snap.get("title"):
                self.lyrics.fetch(snap)
            if prev.get("active") and snap.get("playing") and snap.get("title"):
                icon = ("image", self.media_image) if self.media_image else ("glyph", G.MUSIC, self.accent)
                self.show_hud("track", icon, snap["title"], snap.get("artist", ""), duration=2600)
        self._resolve()

    def on_lyrics(self, key, lines):
        if key == self.media.get("key") and self.settings.get("lyrics"):
            self.expanded_view.media.setLyrics(lines)

    def on_volume(self, level, muted):
        pct = round(level * 100)
        glyph = G.MUTE if muted else G.VOLUME[0 if pct == 0 else min(3, 1 + int(level * 3))]
        self.show_hud("volume", ("glyph", glyph, FG), "Volume", getattr(self.audio, "device_name", ""),
                      bar=0.0 if muted else level, value="Muted" if muted else str(pct),
                      value_color=SUB if muted else FG)

    def on_brightness(self, percent):
        self.show_hud("brightness", ("glyph", G.BRIGHTNESS, YELLOW), "Brightness", bar=percent / 100,
                      color=YELLOW, value=str(percent))

    def on_lock_key(self, name, on):
        icon = ("text", "⇪", GREEN if on else SUB) if name == "Caps Lock" else ("glyph", G.KEYBOARD, GREEN if on else SUB)
        self.show_hud("locks", icon, name, value="On" if on else "Off", value_color=GREEN if on else SUB, duration=1300)

    def on_focus(self, profile):
        detail = {1: "Priority notifications only", 2: "Alarms only"}.get(profile, "Notifications on")
        on = profile != 0
        self.show_hud("focus", ("glyph", G.MOON, PURPLE if on else SUB), "Do Not Disturb", detail,
                      value="On" if on else "Off", value_color=PURPLE if on else SUB, duration=2000)


    def on_battery(self, percent, plugged):
        prev, self.battery = self.battery, (percent, plugged)
        self.expanded_view.setBattery(percent, plugged)
        if prev is None:
            return
        prev_percent, prev_plugged = prev
        if plugged and not prev_plugged:
            self.show_hud("battery", ("battery", percent, True), "Charging", bar=percent / 100, color=GREEN,
                          value=f"{percent}%", value_color=GREEN, duration=3200, animate=True)
        elif prev_plugged and not plugged:
            self.show_hud("battery", ("battery", percent, False), "On battery", "Power adapter disconnected",
                          value=f"{percent}%", duration=2200)
        elif plugged and percent >= 100 > prev_percent:
            self.show_hud("battery", ("battery", percent, True), "Fully charged", value="100%", value_color=GREEN)
        elif not plugged and (percent <= 20 < prev_percent or percent <= 10 < prev_percent):
            self.show_hud("battery", ("battery", percent, False), "Low battery", "Plug in your charger soon",
                          value=f"{percent}%", value_color=RED, duration=4000)

    def on_privacy(self, state):
        prev, self.privacy = self.privacy, state
        camera, mic = bool(state["camera"]), bool(state["mic"])
        for view in (self.idle_view, self.compact_view, self.expanded_view):
            view.dots.setState(camera, mic)
        if prev is None:
            return
        new_camera = [a for a in state["camera"] if a not in prev["camera"] and a != APP_NAME]
        new_mic = [a for a in state["mic"] if a not in prev["mic"] and a != APP_NAME]
        if new_camera:
            self.show_hud("privacy", ("glyph", G.VIDEO, GREEN), "Camera in use", ", ".join(new_camera),
                          value="●", value_color=GREEN, duration=2600)
        elif new_mic:
            self.show_hud("privacy", ("glyph", G.MIC, ORANGE), "Microphone in use", ", ".join(new_mic),
                          value="●", value_color=ORANGE, duration=2600)

    def on_downloads(self, items):
        self.downloads = items
        if items:
            d = items[0]
            detail = f"{fmt_bytes(d['size'])} · {fmt_bytes(d['speed'])}/s"
            if len(items) > 1:
                detail += f" · {len(items) - 1} more"
            self.activity_view.setSpec(dict(icon=("glyph", G.DOWNLOAD, BLUE), title=d["name"],
                                            subtitle=detail, bar="indeterminate", color=BLUE))
        self._resolve()

    def on_download_done(self, name, path):
        self.show_hud("downloads", ("glyph", G.CHECK, GREEN), "Download complete", name, value="Show",
                      value_color=BLUE, duration=4000, action=lambda: show_in_folder(path))

    def on_fullscreen(self, busy):
        self.fullscreen = busy
        self._apply_visibility()
