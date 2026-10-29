"""Pixel-art Ramanan who lives in the notch. Original sprite inspired by the
Punjabi House character: curly hair, big beard and moustache, wide grin,
yellow shirt with a chain, arms crossed. He blinks, raises his eyebrows and
dances when music is playing ("changa chaka chakaa")."""

import math
import random
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

PALETTE = {
    "H": "#17100d",  # hair / eyebrows
    "S": "#8a5532",  # skin
    "s": "#6a3d22",  # skin shadow / ears / nose
    "B": "#1d1511",  # beard & moustache
    "W": "#f4f0e6",  # eye whites & teeth
    "E": "#0b0b0b",  # pupils
    "M": "#5c1c16",  # mouth
    "Y": "#f3c51b",  # yellow shirt
    "y": "#c9970b",  # shirt shadow / folds
    "C": "#e9e3d2",  # chain
}

# 16 x 19. Row 4 = eyebrows, row 5 = eyes (swapped while blinking / raising brows).
SPRITE = [
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "..HHHHHHHHHHHH..",
    "..HSSSSSHSSSSH..",
    "..SHHHSSSSHHHS..",
    ".sSWEWSSSSWEWSs.",
    ".sSSSSSssSSSSSs.",
    "..SSBBBBBBBBSS..",
    "..BBBWWWWWWBBB..",
    "..BBBBMMMMBBBB..",
    "...BBBBBBBBBB...",
    "....BBBBBBBB....",
    "......SSSS......",
    "...YYYCSSCYYY...",
    ".YYYYYYCCYYYYYY.",
    "YYYYYyyCyyYYYYYY",
    "YYyySSSSSSSyYYYY",
    "YYYYyysssssssyYY",
    "YYYYYyYYYYyYYYYY",
]
ROW_BROWS, ROW_EYES = 4, 5
# Raised brows: they jump up into the forehead row, leaving skin below.
FOREHEAD_RAISED = "..HSHHSSHSHHSH.."
BROWS_RAISED = "..SSSSSSSSSSSS.."
EYES_CLOSED = ".sSHHHSSSSHHHSs."

FISH = [".TTTT.T", "TeYYYTT", ".TTTT.T"]
FISH_COLORS = {"T": "#6fa8b5", "Y": "#e3c04d", "e": "#1b2b30"}


def _render(rows, colors):
    img = QImage(len(rows[0]), len(rows), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                img.setPixelColor(x, y, QColor(colors[ch]))
    return img


def _frame(blink=False, brows_up=False):
    rows = list(SPRITE)
    if brows_up:
        rows[ROW_BROWS - 1] = FOREHEAD_RAISED
        rows[ROW_BROWS] = BROWS_RAISED
    if blink:
        rows[ROW_EYES] = EYES_CLOSED
    return _render(rows, PALETTE)


class Ramanan(QWidget):
    """The sprite. `source()` returns (audio level, playing) like the visualizer."""

    PIXEL = 2

    def __init__(self, source=None, parent=None):
        super().__init__(parent)
        self.source = source or (lambda: (0.0, False))
        self.frames = {(b, r): _frame(b, r) for b in (False, True) for r in (False, True)}
        self.setFixedSize(len(SPRITE[0]) * self.PIXEL, len(SPRITE) * self.PIXEL)
        self._next_blink = time.monotonic() + 2
        self._next_brows = time.monotonic() + 5
        self._timer = QTimer(self, interval=60, timeout=self.update)

    def showEvent(self, _):
        self._timer.start()

    def hideEvent(self, _):
        self._timer.stop()

    def paintEvent(self, _):
        now = time.monotonic()
        level, playing = self.source()
        if now > self._next_blink + 0.14:
            self._next_blink = now + random.uniform(2.5, 5.5)
        if now > self._next_brows + 0.6:
            self._next_brows = now + random.uniform(6, 12)
        blink = self._next_blink <= now
        brows = self._next_brows <= now

        bob = tilt = 0.0
        if playing:  # dance: bounce to the beat, sway, brows on the off-beat
            beat = now * (2.2 + level * 2)
            bob = -abs(math.sin(beat * math.pi)) * (1.5 + level * 3)
            tilt = math.sin(beat * math.pi / 2) * 4
            brows = brows or math.sin(beat * math.pi) > 0.6

        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.translate(self.width() / 2, self.height())
        p.rotate(tilt)
        p.translate(-self.width() / 2, -self.height() + bob)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), self.frames[(blink, brows)])


class MascotScene(QWidget):
    """Ramanan standing in the notch with pixel fish swimming behind him."""

    def __init__(self, source=None, parent=None):
        super().__init__(parent)
        self.fish_img = _render(FISH, FISH_COLORS)
        self.fish = [  # x (0..1), lane y (px), speed (width/s)
            [random.random(), 6, 0.06], [random.random(), 16, 0.09], [random.random(), 26, 0.05]]
        self.bubbles = []
        self.ramanan = Ramanan(source, self)
        self._last = time.monotonic()
        self._timer = QTimer(self, interval=60, timeout=self._tick)

    def showEvent(self, _):
        self._last = time.monotonic()
        self._timer.start()

    def hideEvent(self, _):
        self._timer.stop()

    def resizeEvent(self, _):
        r = self.ramanan
        r.move((self.width() - r.width()) // 2, self.height() - r.height())

    def _tick(self):
        now = time.monotonic()
        dt, self._last = now - self._last, now
        for f in self.fish:
            f[0] -= f[2] * dt
            if f[0] < -0.1:
                f[0], f[2] = 1.05, random.uniform(0.04, 0.1)
        if random.random() < 0.04:
            self.bubbles.append([random.uniform(0.05, 0.95), self.height()])
        for b in self.bubbles:
            b[1] -= 12 * dt
        self.bubbles = [b for b in self.bubbles if b[1] > 2]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        w = self.width()
        fw, fh = self.fish_img.width() * 2, self.fish_img.height() * 2
        for x, lane, _ in self.fish:
            p.drawImage(QRectF(round(x * w), lane, fw, fh), self.fish_img)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(111, 168, 181, 150))
        for x, y in self.bubbles:
            p.drawRect(QRectF(round(x * w), round(y), 2, 2))
