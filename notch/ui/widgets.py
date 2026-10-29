import math
import time

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QAbstractButton, QWidget

from .theme import FG, GREEN, ORANGE, RED, SUB, TRACK, G, icon_font, text_font


class GlyphButton(QAbstractButton):
    def __init__(self, glyph, size=32, glyph_px=16, tooltip="", parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.glyph_px = glyph_px
        self.color = FG
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAttribute(Qt.WA_Hover)
        self.setFocusPolicy(Qt.NoFocus)

    def setGlyph(self, glyph):
        if glyph != self.glyph:
            self.glyph = glyph
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.isEnabled() and (self.isChecked() or self.underMouse()):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 46 if self.isDown() or self.isChecked() else 26))
            p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        p.setPen(self.color if self.isEnabled() else SUB.darker(160))
        p.setFont(icon_font(self.glyph_px))
        p.drawText(self.rect(), Qt.AlignCenter, self.glyph)


class TextLabel(QWidget):
    """Single-line label that elides with "…" instead of growing."""

    def __init__(self, px=13, weight=QFont.Weight.Normal, color=FG, align=Qt.AlignLeft, parent=None):
        super().__init__(parent)
        self._text = ""
        self.color = color
        self.align = align
        self.setFont(text_font(px, weight))
        self.setFixedHeight(self.fontMetrics().height() + 2)
        self.setMinimumWidth(10)

    def setText(self, text):
        if text != self._text:
            self._text = text
            self.update()

    def text(self):
        return self._text

    def setColor(self, color):
        self.color = QColor(color)
        self.update()

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self._text) + 4, self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setPen(self.color)
        p.setFont(self.font())
        text = self.fontMetrics().elidedText(self._text, Qt.ElideRight, self.width())
        p.drawText(self.rect(), self.align | Qt.AlignVCenter, text)


class Bar(QWidget):
    """Rounded progress bar; optionally seekable or indeterminate."""

    seek = Signal(float)

    def __init__(self, thickness=5, seekable=False, parent=None):
        super().__init__(parent)
        self.thickness = thickness
        self.seekable = seekable
        self.value = 0.0
        self.color = FG
        self.dragging = False
        self.indeterminate = False
        self._phase = 0.0
        self._timer = QTimer(self, interval=16, timeout=self._advance)
        self.setFixedHeight(thickness + (10 if seekable else 0))
        if seekable:
            self.setCursor(Qt.PointingHandCursor)

    def setValue(self, value):
        if not self.dragging:
            self.value = max(0.0, min(1.0, value))
            self.update()

    def setColor(self, color):
        self.color = QColor(color)
        self.update()

    def setIndeterminate(self, on):
        self.indeterminate = on
        if on and self.isVisible():
            self._timer.start()
        elif not on:
            self._timer.stop()
        self.update()

    def showEvent(self, _):
        if self.indeterminate:
            self._timer.start()

    def hideEvent(self, _):
        self._timer.stop()

    def _advance(self):
        self._phase = (self._phase + 0.012) % 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.thickness
        track = QRectF(0, (self.height() - h) / 2, self.width(), h)
        p.setPen(Qt.NoPen)
        p.setBrush(TRACK)
        p.drawRoundedRect(track, h / 2, h / 2)
        p.setBrush(self.color)
        if self.indeterminate:
            seg = track.width() * 0.3
            x = -seg + (track.width() + seg) * self._phase
            p.setClipRect(track)
            p.drawRoundedRect(QRectF(x, track.y(), seg, h), h / 2, h / 2)
        elif self.value > 0:
            p.drawRoundedRect(QRectF(0, track.y(), max(h, track.width() * self.value), h), h / 2, h / 2)

    def _seek_to(self, x):
        self.value = max(0.0, min(1.0, x / max(self.width(), 1)))
        self.update()

    def mousePressEvent(self, e):
        if self.seekable and e.button() == Qt.LeftButton:
            self.dragging = True
            self._seek_to(e.position().x())

    def mouseMoveEvent(self, e):
        if self.dragging:
            self._seek_to(e.position().x())

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            self.seek.emit(self.value)


class Visualizer(QWidget):
    """Equalizer-style bars driven by the output peak level."""

    def __init__(self, bars=4, bar_width=3, gap=3, source=None, parent=None):
        super().__init__(parent)
        self.source = source or (lambda: (0.0, False))
        self.bar_width = bar_width
        self.gap = gap
        self.color = FG
        self.levels = [0.15] * bars
        self._speeds = [1.7 + 0.9 * i for i in range(bars)]
        self._timer = QTimer(self, interval=33, timeout=self._tick)
        self.setFixedSize(bars * bar_width + (bars - 1) * gap, 18)

    def setColor(self, color):
        self.color = QColor(color)

    def showEvent(self, _):
        self._timer.start()

    def hideEvent(self, _):
        self._timer.stop()

    def _tick(self):
        level, playing = self.source()
        t = time.monotonic()
        for i, speed in enumerate(self._speeds):
            if playing:
                wobble = 0.45 + 0.55 * abs(math.sin(t * speed + i * 1.3))
                target = max(0.18, min(1.0, (0.25 + level * 1.5) * wobble))
            else:
                target = 0.15
            self.levels[i] += (target - self.levels[i]) * 0.35
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        h = self.height()
        for i, lv in enumerate(self.levels):
            bh = max(self.bar_width, h * lv)
            x = i * (self.bar_width + self.gap)
            p.drawRoundedRect(QRectF(x, (h - bh) / 2, self.bar_width, bh), self.bar_width / 2, self.bar_width / 2)


class AlbumArt(QWidget):
    def __init__(self, size, radius, parent=None):
        super().__init__(parent)
        self.radius = radius
        self.image = None
        self._scaled = None
        self.setFixedSize(size, size)

    def setImage(self, image):
        self.image = image if image is not None and not image.isNull() else None
        self._scaled = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        p.setClipPath(path)
        if self.image is None:
            p.fillRect(self.rect(), QColor(44, 44, 46))
            p.setPen(SUB)
            p.setFont(icon_font(int(self.width() * 0.42)))
            p.drawText(self.rect(), Qt.AlignCenter, G.MUSIC)
            return
        if self._scaled is None:
            dpr = self.devicePixelRatioF()
            pix = QPixmap.fromImage(self.image).scaled(
                self.size() * dpr, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            pix.setDevicePixelRatio(dpr)
            self._scaled = pix
        pw = self._scaled.width() / self._scaled.devicePixelRatio()
        ph = self._scaled.height() / self._scaled.devicePixelRatio()
        p.drawPixmap(QRectF((self.width() - pw) / 2, (self.height() - ph) / 2, pw, ph),
                     self._scaled, QRectF(self._scaled.rect()))


class PrivacyDots(QWidget):
    """Green dot = camera in use, orange dot = microphone in use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.camera = False
        self.mic = False
        self.setFixedSize(22, 10)

    def setState(self, camera, mic):
        self.camera, self.mic = camera, mic
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        dots = [c for on, c in ((self.camera, GREEN), (self.mic, ORANGE)) if on]
        x = self.width() - 8
        for color in reversed(dots):
            p.setBrush(color)
            p.drawEllipse(QRectF(x, 1, 8, 8))
            x -= 12


class IconSlot(QWidget):
    """Leading icon in HUDs: a glyph, a text symbol, an image or a battery."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.spec = ("glyph", "", FG)
        self._fill = 0.0
        self._anim = QVariantAnimation(self, duration=1100, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_fill)

    def _set_fill(self, v):
        self._fill = v
        self.update()

    def setSpec(self, spec, animate=False):
        """animate=True plays the battery 'filling up' charge animation."""
        self.spec = spec
        if spec[0] == "battery":
            target = spec[1] / 100
            if animate:
                self._anim.stop()
                self._anim.setStartValue(0.0)
                self._anim.setEndValue(target)
                self._anim.start()
            elif self._anim.state() != QVariantAnimation.Running:
                self._fill = target
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        kind = self.spec[0]
        if kind == "glyph":
            p.setPen(self.spec[2])
            p.setFont(icon_font(20))
            p.drawText(self.rect(), Qt.AlignCenter, self.spec[1])
        elif kind == "text":
            p.setPen(self.spec[2])
            p.setFont(text_font(22, QFont.Weight.DemiBold))
            p.drawText(self.rect(), Qt.AlignCenter, self.spec[1])
        elif kind == "image":
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 8, 8)
            p.setClipPath(path)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            img = self.spec[1]
            p.drawImage(QRectF(self.rect()), img, QRectF(img.rect()))
        elif kind == "battery":
            self._paint_battery(p, self.spec[1], self.spec[2])

    def _paint_battery(self, p, percent, charging):
        body = QRectF(2, 10, 26, 14)
        color = GREEN if charging else (RED if percent <= 20 else FG)
        p.setPen(QPen(SUB, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body, 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(SUB)
        p.drawRoundedRect(QRectF(29.5, 14.5, 2.5, 5), 1, 1)
        inner = body.adjusted(2, 2, -2, -2)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(inner.x(), inner.y(), max(2.0, inner.width() * self._fill), inner.height()), 2, 2)
        if charging:
            p.setPen(QColor(0, 0, 0))
            p.setFont(icon_font(11))
            p.drawText(body, Qt.AlignCenter, G.BOLT)


def accent_from_image(image):
    """Most vivid colour of the artwork, brightened so it reads on black."""
    if image is None or image.isNull():
        return QColor(FG)
    small = image.scaled(24, 24, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(
        QImage.Format_RGB32)
    r = g = b = total = 0.0
    for y in range(small.height()):
        for x in range(small.width()):
            c = QColor(small.pixel(x, y))
            w = c.saturationF() ** 2 * c.valueF()
            r, g, b, total = r + c.redF() * w, g + c.greenF() * w, b + c.blueF() * w, total + w
    if total < 1.5:
        return QColor(FG)
    color = QColor.fromRgbF(r / total, g / total, b / total)
    h, s, v = color.hsvHueF(), color.hsvSaturationF(), color.valueF()
    return QColor.fromHsvF(max(h, 0), min(s * 1.1, 0.8), max(v, 0.9))
