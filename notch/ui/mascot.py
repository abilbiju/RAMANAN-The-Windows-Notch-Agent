"""Pixel-art Ramanan who lives in the notch. Original sprite inspired by the
Punjabi House character: curly hair, big beard and moustache, wide grin,
yellow shirt with a chain, arms crossed. He blinks, raises his eyebrows,
dances to music with real moves ("changa chaka chakaa") and has moods:
sleepy when the PC is idle, sweating on low battery, partying when something
finishes and shocked when the camera turns on."""

import ctypes
import math
import random
import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer
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
    "w": "#8fd3ff",  # sweat
    "z": "#c9d6ff",  # sleepy Zs
}
CONFETTI = ["#ff453a", "#30d158", "#0a84ff", "#ffd60a", "#bf5af2", "#ff9f0a"]

# 16 x 19 body; the canvas adds MARGIN columns each side so the arms can swing out.
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
    "YYyySSSSSSSyYYYY",  # 16-18: arms crossed
    "YYYYyysssssssyYY",
    "YYYYYyYYYYyYYYYY",
]
ARMLESS = {16: ".YYYYYyyyYYYYYY.", 17: ".YYYYYYYYYYYYYY.", 18: ".YYYYyYYYYyYYYY."}
MARGIN = 4
W, H = len(SPRITE[0]) + 2 * MARGIN, len(SPRITE)

# Face rows swapped in per expression (row index -> 16-wide row).
FOREHEAD_RAISED = "..HSHHSSHSHHSH.."
BROWS_RAISED = "..SSSSSSSSSSSS.."
# Closed eyes: lids one row lower than the eyes, so they don't merge with the brows.
EYES_CLOSED = {5: ".sSSSSSSSSSSSSs.", 6: ".sSHHHSssSHHHSs."}
FACES = {
    "grin": {},
    "blink": EYES_CLOSED,
    "brows": {3: FOREHEAD_RAISED, 4: BROWS_RAISED},
    "happy": {4: "..SSHSSSSSSHSS..", 5: ".sSHSHSSSSHSHSs.", 8: "..BBWWWWWWWWBB..", 9: "..BBBMMMMMMBBB.."},
    "sleep": {**EYES_CLOSED, 8: "..BBBBBBBBBBBB..", 9: "..BBBBBMMBBBBB.."},
    "worried": {3: "..HSSHSSHSHSSH..", 4: "..SHHSSSSSSHHS..", 9: "..BBBBBBBBBBBB.."},
    "shock": {3: FOREHEAD_RAISED, 4: BROWS_RAISED, 5: ".sWWEWSSSSWEWWs.", 6: ".sSWWSSssSSWWSs.",
              8: "..BBBBMMMMBBBB..", 9: "..BBBBMMMMBBBB.."},
}

# Arm poses for the left arm as (elbow, hand) in canvas pixels; the right arm
# is mirrored. Each joint is the top-left of a 2x2 stamp. "cross" keeps the
# original folded arms.
SHOULDER = (4, 14)
POSES = {
    "down": ((3, 16), (3, 17)),
    "hip": ((1, 16), (4, 17)),
    "up": ((2, 10), (3, 5)),          # bhangra: hands beside the ears
    "pump": ((3, 9), (3, 3)),         # fist straight up
    "out": ((1, 13), (0, 11)),
    "point": ((2, 11), (0, 6)),       # disco point, up and out
    "low": ((2, 16), (0, 17)),        # disco point, down and out
    "flex": ((1, 15), (2, 10)),
    "chest": ((2, 16), (7, 15)),
    "cheeks": ((3, 13), (5, 8)),      # hands on the face
}

# Dance moves: one frame per beat as (left pose, right pose, dx, dy, tilt).
MOVES = {
    "headbob": [("cross", "cross", 0, -1, -2), ("cross", "cross", 0, 0, 2)],
    "sway": [("chest", "hip", -2, 0, -4), ("hip", "chest", 2, 0, 4)],
    "bhangra": [("up", "pump", -1, -2, -4), ("pump", "up", 1, 0, 4)],
    "disco": [("point", "hip", 0, -1, -5), ("low", "hip", 0, 0, 2),
              ("point", "hip", 0, -1, -5), ("low", "hip", 0, 0, 2),
              ("hip", "point", 0, -1, 5), ("hip", "low", 0, 0, -2),
              ("hip", "point", 0, -1, 5), ("hip", "low", 0, 0, -2)],
    "wave": [("out", "out", 0, -1, 0), ("up", "down", 0, 0, -4),
             ("out", "out", 0, -1, 0), ("down", "up", 0, 0, 4)],
    "flex": [("flex", "flex", 0, -2, 0), ("chest", "chest", 0, 0, 0)],
}
CALM_MOVES = ("headbob", "sway")
BIG_MOVES = ("bhangra", "disco", "wave", "flex")
BEATS_PER_SECOND = 1.9   # ~114 bpm, a comfortable groove for most songs
BEATS_PER_MOVE = 8


def _render(rows, colors):
    img = QImage(len(rows[0]), len(rows), QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                img.setPixelColor(x, y, QColor(colors[ch]))
    return img


def _stamp(img, x, y, color):
    for px in (x, x + 1):
        for py in (y, y + 1):
            if 0 <= px < W and 0 <= py < H:
                img.setPixelColor(px, py, color)


def _line(img, a, b, color):
    steps = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
    for i in range(steps + 1):
        _stamp(img, round(a[0] + (b[0] - a[0]) * i / steps), round(a[1] + (b[1] - a[1]) * i / steps), color)


def _arm(img, pose, mirror):
    elbow, hand = POSES[pose]
    flip = (lambda p: (W - 2 - p[0], p[1])) if mirror else (lambda p: p)
    sleeve, skin = QColor(PALETTE["Y"]), QColor(PALETTE["S"])
    _line(img, flip(SHOULDER), flip(elbow), sleeve)
    _line(img, flip(elbow), flip(hand), skin)


def compose(face="grin", left="cross", right="cross"):
    """One frame of Ramanan as a W x H image."""
    rows = list(SPRITE)
    for i, row in FACES[face].items():
        rows[i] = row
    crossed = left == "cross" and right == "cross"
    if not crossed:
        for i, row in ARMLESS.items():
            rows[i] = row
    pad = "." * MARGIN
    img = _render([pad + r + pad for r in rows], PALETTE)
    if not crossed:
        _arm(img, "down" if left == "cross" else left, False)
        _arm(img, "down" if right == "cross" else right, True)
    return img


def _put(img, x, y, color):
    if 0 <= x < W and 0 <= y < H and img.pixelColor(x, y).alpha() == 0:
        img.setPixelColor(x, y, color)


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds():
    info = _LastInput(ctypes.sizeof(_LastInput))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


class Mood(QObject):
    """Shared by every Ramanan on screen. Listens to the bus and decides how he
    feels: party / shock are short reactions, sweat and sleep are states."""

    SLEEP_AFTER = 120
    PARTY_FOR = 5.0
    SHOCK_FOR = 3.0

    def __init__(self, bus=None):
        super().__init__()
        self._party_until = self._shock_until = 0.0
        self._low_battery = False
        self._battery = None
        self._camera = False
        self._idle, self._idle_checked = 0.0, 0.0
        if bus is not None:
            bus.battery.connect(self._on_battery)
            bus.privacy.connect(self._on_privacy)
            bus.download_done.connect(lambda *_: self.celebrate())

    def celebrate(self):
        self._party_until = time.monotonic() + self.PARTY_FOR

    def _on_battery(self, percent, plugged):
        self._low_battery = percent <= 20 and not plugged
        if plugged and percent >= 100 and self._battery is not None and self._battery < 100:
            self.celebrate()
        self._battery = percent

    def _on_privacy(self, state):
        camera = bool(state.get("camera"))
        if camera and not self._camera:
            self._shock_until = time.monotonic() + self.SHOCK_FOR
        self._camera = camera

    def current(self, playing):
        now = time.monotonic()
        if now < self._party_until:
            return "party"
        if now < self._shock_until:
            return "shock"
        if playing:
            return "dance"
        if self._low_battery:
            return "sweat"
        if now - self._idle_checked > 2:
            self._idle_checked = now
            try:
                self._idle = idle_seconds()
            except (AttributeError, OSError):
                self._idle = 0.0
        return "sleep" if self._idle >= self.SLEEP_AFTER else "idle"


class Ramanan(QWidget):
    """The sprite. `source()` returns (audio level, playing) like the visualizer."""

    PIXEL = 2

    def __init__(self, source=None, mood=None, parent=None):
        super().__init__(parent)
        self.source = source or (lambda: (0.0, False))
        self.mood = mood or Mood()
        self.setFixedSize(W * self.PIXEL, H * self.PIXEL)
        self._next_blink = time.monotonic() + 2
        self._next_brows = time.monotonic() + 5
        self._energy = 0.0
        self._move, self._move_until = "headbob", 0
        self._cache = {}
        self._timer = QTimer(self, interval=60, timeout=self.update)

    def showEvent(self, _):
        self._timer.start()

    def hideEvent(self, _):
        self._timer.stop()

    def _frame(self, face, left, right):
        key = (face, left, right)
        if key not in self._cache:
            self._cache[key] = compose(face, left, right)
        return self._cache[key]

    def _dance(self, now, level, beat):
        """Pick a move every few bars: calm ones for quiet songs, big ones when it's loud."""
        self._energy += (level - self._energy) * 0.05
        if beat >= self._move_until:
            pool = BIG_MOVES if self._energy > 0.18 else CALM_MOVES
            self._move = random.choice([m for m in pool if m != self._move] or pool)
            self._move_until = beat + BEATS_PER_MOVE
        steps = MOVES[self._move]
        return steps[beat % len(steps)]

    def pose(self, now, level, playing):
        """(image, dx, dy, tilt, effects) for this instant."""
        mood = self.mood.current(playing)
        if now > self._next_blink + 0.14:
            self._next_blink = now + random.uniform(2.5, 5.5)
        if now > self._next_brows + 0.6:
            self._next_brows = now + random.uniform(6, 12)
        face = "blink" if self._next_blink <= now else "brows" if self._next_brows <= now else "grin"

        if mood == "dance":
            beat_pos = now * BEATS_PER_SECOND
            beat, frac = int(beat_pos), beat_pos % 1
            left, right, dx, dy, tilt = self._dance(now, level, beat)
            bounce = -abs(math.sin(frac * math.pi)) * (1 + level * 2.5)
            if face == "grin" and frac < 0.3 and beat % 2:
                face = "brows"
            return self._frame(face, left, right), dx, dy + bounce, tilt, None
        if mood == "party":
            beat = int(now * 4)
            left, right = ("pump", "up") if beat % 2 else ("up", "pump")
            hop = -abs(math.sin(now * 4 * math.pi)) * 3
            return self._frame("happy", left, right), 0, hop, 0, "confetti"
        if mood == "shock":
            jolt = -2 if self.mood._shock_until - now > self.mood.SHOCK_FOR - 0.3 else 0
            return self._frame("shock", "cheeks", "cheeks"), 0, jolt, 0, None
        if mood == "sweat":
            shiver = 1 if int(now * 10) % 7 == 0 else 0
            return self._frame("blink" if face == "blink" else "worried", "cross", "cross"), shiver, 0, 0, "sweat"
        if mood == "sleep":
            breathe = math.sin(now * 1.6) * 0.8 + 1
            return self._frame("sleep", "down", "down"), 0, breathe, 3, "zzz"
        return self._frame(face, "cross", "cross"), 0, 0, 0, None

    @staticmethod
    def effects(img, kind, now):
        """Overlay pixels drawn only where the sprite is transparent."""
        if kind is None:
            return img
        img = img.copy()
        if kind == "sweat":
            y = 3 + int((now * 5) % 6)
            _put(img, 19, y, QColor(PALETTE["w"]))
            _put(img, 19, y + 1, QColor(PALETTE["w"]))
        elif kind == "zzz":
            for offset in (0.0, 0.5):
                t = (now * 0.4 + offset) % 1
                x, y = 19 + round(t), 9 - round(t * 8)
                color = QColor(PALETTE["z"])
                color.setAlphaF(1 - t * 0.7)
                for dx, dy in ((0, 0), (1, 0), (2, 0), (3, 0), (2, 1), (1, 2), (0, 3), (1, 3), (2, 3), (3, 3)):
                    _put(img, x + dx, y + dy, color)
        elif kind == "confetti":
            rng = random.Random(int(now * 8))
            for _ in range(10):
                _put(img, rng.randrange(W), rng.randrange(H - 4), QColor(rng.choice(CONFETTI)))
        return img

    def paintEvent(self, _):
        now = time.monotonic()
        level, playing = self.source()
        img, dx, dy, tilt, fx = self.pose(now, level, playing)
        img = self.effects(img, fx, now)

        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.translate(self.width() / 2, self.height())
        p.rotate(tilt)
        p.translate(-self.width() / 2 + dx * self.PIXEL, -self.height() + dy)
        p.drawImage(QRectF(0, 0, self.width(), self.height()), img)


class MascotScene(QWidget):
    """Ramanan standing in the notch with pixel fish swimming behind him."""

    def __init__(self, source=None, mood=None, parent=None):
        super().__init__(parent)
        self.fish_img = _render(FISH, FISH_COLORS)
        self.fish = [  # x (0..1), lane y (px), speed (width/s)
            [random.random(), 6, 0.06], [random.random(), 16, 0.09], [random.random(), 26, 0.05]]
        self.bubbles = []
        self.ramanan = Ramanan(source, mood, self)
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


FISH = [".TTTT.T", "TeYYYTT", ".TTTT.T"]
FISH_COLORS = {"T": "#6fa8b5", "Y": "#e3c04d", "e": "#1b2b30"}
