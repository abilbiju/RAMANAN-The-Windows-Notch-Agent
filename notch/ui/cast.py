"""The cast: every pixel character that can live in the notch. They are all
drawn on Ramanan's 16 x 19 grid, so they share his arm poses, dance moves and
moods. On top of that each one has its own palette and faces, an optional prop
in hand, a signature action (played now and then while idle, and as one of the
dance moves) and something drifting past behind him in the expanded notch.

All fan tributes drawn in code; none of these characters belong to this project."""

import math
import random
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from . import mascot
from .mascot import BEATS_PER_SECOND, BEATS_PER_MOVE, BIG_MOVES, CALM_MOVES, MARGIN, MOVES, POSES, H, W

GRID_W = W - 2 * MARGIN
WHITE = "#f7f7f7"


@dataclass
class Prop:
    rows: list
    colors: dict
    offset: tuple          # from the hand's top-left pixel, or canvas position when at="body"
    at: str = "right"      # right | body


@dataclass
class Character:
    key: str
    name: str
    source: str
    sprite: list
    palette: dict
    armless: dict
    sleeve: str
    hand: str
    faces: dict = field(default_factory=dict)
    held: Prop = None      # carried in the right hand whenever that arm is out
    tags: dict = field(default_factory=dict)       # tag -> {rows, face, prop, fx}
    signature: list = field(default_factory=list)  # (left, right, dx, dy, tilt, tag) per beat
    backdrop: tuple = None  # (rows, colors, count) drifting behind in the expanded notch

    def __post_init__(self):
        rows = [*self.sprite, *self.armless.values()]
        rows += [r for face in self.faces.values() for r in face.values()]
        rows += [r for tag in self.tags.values() for r in tag.get("rows", {}).values()]
        assert len(self.sprite) == H, f"{self.key}: {len(self.sprite)} rows"
        for r in rows:
            assert len(r) == GRID_W, f"{self.key}: {r!r} is {len(r)} wide"
            missing = set(r) - set(self.palette) - {"."}
            assert not missing, f"{self.key}: {r!r} uses {missing}"


def _sub(row, cols, ch):
    return "".join(ch if x in cols else c for x, c in enumerate(row))


def derive_faces(sprite, mouths, skin="S", lid="H", hair="H", **overrides):
    """The standard expressions worked out from the base face (eyes on row 5,
    brows on row 4): lids for blink, brows moved up a row, ^ ^ eyes for happy,
    inner brows up for worried. `mouths` gives the rows for happy / closed /
    flat / open; `overrides` replaces rows of any face by name."""
    eyes, brows = 5, 4
    eye, brow, above = sprite[eyes], sprite[brows], sprite[brows - 1]
    cols = [x for x, c in enumerate(eye) if c in "WE"]
    pupils = [x for x in cols if eye[x] == "E"]
    whites = [x for x in cols if eye[x] == "W"]
    brow_cols = [x for x in range(3, GRID_W - 3) if brow[x] == hair]
    inner = [max(x for x in brow_cols if x < 8), min(x for x in brow_cols if x >= 8)]

    blink = {eyes: _sub(eye, cols, skin), eyes + 1: _sub(sprite[eyes + 1], cols, lid)}
    raised = {brows - 1: _sub(above, brow_cols, hair), brows: _sub(brow, brow_cols, skin)}
    faces = {
        "grin": {},
        "blink": blink,
        "brows": raised,
        "happy": {brows: _sub(_sub(brow, brow_cols, skin), pupils, lid),
                  eyes: _sub(_sub(eye, whites, lid), pupils, skin), **mouths["happy"]},
        "sleep": {**blink, **mouths["closed"]},
        "worried": {brows - 1: _sub(above, inner, hair), brows: _sub(brow, inner, skin), **mouths["flat"]},
        "shock": {**raised, **mouths["open"]},
    }
    for name, rows in overrides.items():
        faces[name] = {**faces.get(name, {}), **rows}
    return faces


def _hand(pose, mirror):
    x, y = POSES["down" if pose == "cross" else pose][1]
    return (W - 2 - x, y) if mirror else (x, y)


def _draw(img, rows, colors, x0, y0):
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors and 0 <= x0 + x < W and 0 <= y0 + y < H:
                img.setPixelColor(x0 + x, y0 + y, QColor(colors[ch]))


def _arm(img, pose, mirror, sleeve, hand):
    elbow, tip = POSES[pose]
    flip = (lambda p: (W - 2 - p[0], p[1])) if mirror else (lambda p: p)
    mascot._line(img, flip(mascot.SHOULDER), flip(elbow), QColor(sleeve))
    mascot._line(img, flip(elbow), flip(tip), QColor(hand))


def compose(char, face="grin", left="cross", right="cross", tag=None):
    """One frame of `char` as a W x H image."""
    spec = char.tags.get(tag, {})
    rows = list(char.sprite)
    for i, row in {**char.faces[spec.get("face", face)], **spec.get("rows", {})}.items():
        rows[i] = row
    crossed = left == "cross" and right == "cross"
    if not crossed:
        for i, row in char.armless.items():
            rows[i] = row
    pad = "." * MARGIN
    img = mascot._render([pad + r + pad for r in rows], char.palette)
    colors = char.palette[char.sleeve], char.palette[char.hand]
    if not crossed:
        _arm(img, "down" if left == "cross" else left, False, *colors)
        _arm(img, "down" if right == "cross" else right, True, *colors)
    prop = spec.get("prop", char.held if right not in ("cross", "cheeks") else None)
    if prop is not None:
        if prop.at == "body":
            _draw(img, prop.rows, prop.colors, *prop.offset)
        else:
            hx, hy = _hand(right, True)
            _draw(img, prop.rows, prop.colors, hx + prop.offset[0], hy + prop.offset[1])
    return img


# --- effects drawn around the sprite (only on empty pixels) -----------------

def _ray(img, a, b, color):
    steps = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
    for i in range(steps + 1):
        mascot._put(img, round(a[0] + (b[0] - a[0]) * i / steps), round(a[1] + (b[1] - a[1]) * i / steps), color)


LETTER_H = ["X.X", "X.X", "XXX", "X.X", "X.X"]
LETTER_A = [".X.", "X.X", "XXX", "X.X", "X.X"]


def _glow(img, hand, core, ring, now):
    """Light up a hand (the canvas has no room for beams past it): bright palm,
    flickering halo around it."""
    hx, hy = hand
    for dx in (0, 1):
        for dy in (0, 1):
            if 0 <= hx + dx < W and 0 <= hy + dy < H:
                img.setPixelColor(hx + dx, hy + dy, QColor(core))
    if int(now * 12) % 2:
        for dx in range(-1, 3):
            for dy in range(-1, 3):
                mascot._put(img, hx + dx, hy + dy, QColor(ring))


def _fx(img, kind, now, char, left, right):
    if kind in ("web", "webl"):
        mirror = kind == "web"
        hx, hy = _hand(right if mirror else left, mirror)
        start = (hx + 1, hy - 1) if mirror else (hx, hy - 1)
        _ray(img, start, (W - 3 if mirror else 2, 0), QColor(WHITE))
    elif kind in ("blast", "blastl"):
        mirror = kind == "blast"
        _glow(img, _hand(right if mirror else left, mirror), "#e9fdff", "#5fe3f5", now)
    elif kind == "thrust":
        flick = int(now * 14) % 2
        for pose, mirror in ((left, False), (right, True)):
            hx, hy = _hand(pose, mirror)
            for dx in (0, 1):
                mascot._put(img, hx + dx, hy + 2, QColor("#e9fdff"))
                mascot._put(img, hx + dx, hy + 3 + flick, QColor("#5fe3f5"))
    elif kind == "cape":
        cape = QColor(char.palette["K"])
        for x in [*range(MARGIN), *range(W - MARGIN, W)]:
            top = next((y for y in range(H) if img.pixelColor(x, y).alpha()), None)
            if top is not None:
                for y in range(top + 2, H):
                    mascot._put(img, x, y, cape)
    elif kind == "haha":
        color = QColor("#7ee08a")
        up = int(now * 4) % 2
        for letter, x0, y0 in ((LETTER_H, 0, 1 + up * 2), (LETTER_A, W - 3, 3 - up * 2)):
            for y, row in enumerate(letter):
                for x, ch in enumerate(row):
                    if ch == "X":
                        mascot._put(img, x0 + x, y0 + y, color)
    elif kind == "pew":
        for pose, mirror in ((left, False), (right, True)):
            _glow(img, _hand(pose, mirror), "#fff3b0", "#ff9f0a", now)
    elif kind == "spark":
        hx, hy = _hand(right, True)
        rng = random.Random(int(now * 10))
        for _ in range(4):
            mascot._put(img, hx + rng.randint(-2, 3), hy + rng.randint(-3, 1),
                        QColor(rng.choice(["#ffd60a", "#ff9f0a", WHITE])))
    elif kind == "glint":
        if int(now * 6) % 3 == 0:
            img.setPixelColor(MARGIN + 4, 6, QColor(WHITE))
            img.setPixelColor(MARGIN + 3, 5, QColor(WHITE))


class CastMember(mascot.Ramanan):
    """Any character from the cast, with Ramanan's moods and dancing plus a
    signature action now and then."""

    def __init__(self, char, source=None, mood=None, parent=None):
        self.char = char
        super().__init__(source, mood, parent)
        self._quirk_at = time.monotonic() + random.uniform(8, 16)
        self._arms = ("cross", "cross")

    def setCharacter(self, char):
        if char is not self.char:
            self.char = char
            self._cache.clear()
            self._move_until = 0
            self.update()

    def _frame(self, face, left, right, tag=None):
        self._arms = (left, right)
        key = (face, left, right, tag)
        if key not in self._cache:
            self._cache[key] = compose(self.char, face, left, right, tag)
        return self._cache[key]

    def _dance(self, now, level, beat):
        self._energy += (level - self._energy) * 0.05
        if beat >= self._move_until:
            pool = BIG_MOVES + (("signature",) if self.char.signature else ())
            pool = pool if self._energy > 0.18 else CALM_MOVES
            self._move = random.choice([m for m in pool if m != self._move] or pool)
            self._move_until = beat + BEATS_PER_MOVE
        steps = self.char.signature if self._move == "signature" else MOVES[self._move]
        return (*steps[beat % len(steps)], None)[:6]

    def _face(self, now):
        if now > self._next_blink + 0.14:
            self._next_blink = now + random.uniform(2.5, 5.5)
        if now > self._next_brows + 0.6:
            self._next_brows = now + random.uniform(6, 12)
        return "blink" if self._next_blink <= now else "brows" if self._next_brows <= now else "grin"

    def _tag_fx(self, tag):
        return self.char.tags.get(tag, {}).get("fx", tag)

    def pose(self, now, level, playing):
        mood = self.mood.current(playing)
        if mood == "dance":
            face = self._face(now)
            beat_pos = now * BEATS_PER_SECOND
            beat, frac = int(beat_pos), beat_pos % 1
            left, right, dx, dy, tilt, tag = self._dance(now, level, beat)
            bounce = -abs(math.sin(frac * math.pi)) * (1 + level * 2.5)
            if face == "grin" and frac < 0.3 and beat % 2:
                face = "brows"
            return self._frame(face, left, right, tag), dx, dy + bounce, tilt, self._tag_fx(tag)
        sig = self.char.signature
        if mood == "idle" and sig and now >= self._quirk_at:
            i = int((now - self._quirk_at) * BEATS_PER_SECOND)
            if i < len(sig):
                left, right, dx, dy, tilt, tag = (*sig[i], None)[:6]
                return self._frame(self._face(now), left, right, tag), dx, dy, tilt, self._tag_fx(tag)
            self._quirk_at = now + random.uniform(15, 30)
        img, dx, dy, tilt, fx = super().pose(now, level, playing)
        return img, dx, dy, tilt, fx

    def effects(self, img, kind, now):
        if kind in (None, "sweat", "zzz", "confetti"):
            return mascot.Ramanan.effects(img, kind, now)
        img = img.copy()
        _fx(img, kind, now, self.char, *self._arms)
        return img


class MascotScene(QWidget):
    """The character standing in the notch with their backdrop drifting past
    behind (Ramanan's fish also blow bubbles)."""

    LANES = (6, 16, 26)

    def __init__(self, char, source=None, mood=None, parent=None):
        super().__init__(parent)
        self.actor = CastMember(char, source, mood, self)
        self._last = time.monotonic()
        self._timer = QTimer(self, interval=60, timeout=self._tick)
        self.setCharacter(char, force=True)

    def setCharacter(self, char, force=False):
        if char is self.actor.char and not force:
            return
        self.actor.setCharacter(char)
        rows, colors, count = char.backdrop or ([], {}, 0)
        self.drift_img = mascot._render(rows, colors) if rows else None
        lanes = self.LANES if count > 1 else (12,)  # a lone vehicle rides in the middle
        self.drifters = [[random.random(), lanes[i % len(lanes)], random.uniform(0.04, 0.1)] for i in range(count)]
        self.bubbles = []
        self.update()

    def showEvent(self, _):
        self._last = time.monotonic()
        self._timer.start()

    def hideEvent(self, _):
        self._timer.stop()

    def resizeEvent(self, _):
        r = self.actor
        r.move((self.width() - r.width()) // 2, self.height() - r.height())

    def _tick(self):
        now = time.monotonic()
        dt, self._last = now - self._last, now
        for f in self.drifters:
            f[0] -= f[2] * dt
            if f[0] < -0.15:
                f[0], f[2] = 1.05, random.uniform(0.04, 0.1)
        if self.actor.char is RAMANAN and random.random() < 0.04:
            self.bubbles.append([random.uniform(0.05, 0.95), self.height()])
        for b in self.bubbles:
            b[1] -= 12 * dt
        self.bubbles = [b for b in self.bubbles if b[1] > 2]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        w = self.width()
        if self.drift_img is not None:
            fw, fh = self.drift_img.width() * 2, self.drift_img.height() * 2
            for x, lane, _ in self.drifters:
                p.drawImage(QRectF(round(x * w), lane, fw, fh), self.drift_img)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(111, 168, 181, 150))
        for x, y in self.bubbles:
            p.drawRect(QRectF(round(x * w), round(y), 2, 2))


# --- the cast ---------------------------------------------------------------

SKIN_EYES = {"W": "#f4f0e6", "E": "#0b0b0b"}

RAMANAN = Character(
    "ramanan", "Ramanan", "Punjabi House (2002)",
    mascot.SPRITE, mascot.PALETTE, mascot.ARMLESS, "Y", "S", faces=mascot.FACES,
    backdrop=(mascot.FISH, mascot.FISH_COLORS, 3),
)

# Sulaiman, the mechanic who can't fix the road roller. Toothy grin, towel on the shoulder, spanner.
_pappu = [
    "................",
    "....HHHHHHHH....",
    "...HHSSSSSSHH...",
    "..HSSSSSSSSSSH..",
    "..SHHHSSSSHHHS..",
    ".sSWEWSSSSWEWSs.",
    ".sSSSSSssSSSSSs.",
    "..SSSSSssSSSSS..",
    "..SSSHHHHHHSSS..",
    "..SSWWWWWWWWSS..",
    "...SSMMMMMMSS...",
    "....SSSSSSSS....",
    "......SSSS......",
    "..RrRBBSSBBBBB..",
    ".RrRrBBBBBBBBBB.",
    "BrRrRBbBBBBgBBBB",
    "BBbbSSSSSSSbBBBB",
    "BBBBbbsssssssbBB",
    "BBBBBbBBBBbBBBBB",
]
PAPPU = Character(
    "pappu", "Kuthiravattom Pappu", "Vellanakalude Naadu (1988)",
    _pappu,
    {"H": "#141010", "S": "#7b4a2b", "s": "#5e351d", **SKIN_EYES, "M": "#4a1612",
     "B": "#4f7fae", "b": "#365f88", "R": "#c23b2e", "r": "#ead9b8", "g": "#2b2b2b"},
    {16: ".BBBBBbbbBBBBBB.", 17: ".BBBBBBBBBBBBBB.", 18: ".BBBBbBBBBbBBBB."}, "B", "S",
    faces=derive_faces(_pappu, {
        "happy": {9: "..SWWWWWWWWWWS..", 10: "...SMMMMMMMMS..."},
        "closed": {9: "..SSSSSSSSSSSS..", 10: "...SSSSMMSSSS..."},
        "flat": {9: "..SSSSSSSSSSSS..", 10: "...SSSMMMMSSS..."},
        "open": {9: "..SSSSMMMMSSSS..", 10: "...SSSMMMMSSS..."},
    }),
    held=Prop(["k.k", "kkk", ".k.", ".k."], {"k": "#aab1ba"}, (0, -3)),
    signature=[("hip", "pump", 0, -1, -2), ("hip", "chest", 0, 0, 2, "spark"),
               ("hip", "pump", 0, -1, -2), ("hip", "chest", 0, 0, 2, "spark"),
               ("hip", "pump", 0, -1, -2), ("hip", "chest", 0, 0, 2, "spark"),
               ("hip", "up", 0, -1, 0)],
    backdrop=([".....kk...", "...YYYYYY.", "...Y..Y.Y.", "dd.YYYYYYY", "dDdYYYYYYY", "dd....oo.."],
              {"Y": "#e9b625", "k": "#3a3a3a", "d": "#6d7075", "D": "#9aa0a6", "o": "#2a2a2a"}, 1),
)

# Manavalan: flashy pink shirt, gold chain, shades he keeps adjusting.
_manavalan = [
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "..HHHHHHHHHHHH..",
    "..HHSSSSSSSSHH..",
    "..SHHHSSSSHHHS..",
    ".sKKKKKKKKKKKKs.",
    ".sSKGKKssKKGKSs.",
    "..SSSSSssSSSSS..",
    "..SSSHHHHHHSSS..",
    "..SSSLMMMMLSSS..",
    "...SSSLLLLSSS...",
    "....SSSSSSSS....",
    "......SSSS......",
    "...PPPCSSCPPP...",
    ".PPpPPPCCPPPpPP.",
    "PPPPPqqCqqPpPPPP",
    "PpqqSSSSSSSqPPpP",
    "PPPPqqsssssssqPP",
    "PPpPPqPPPPqPPPpP",
]
_shades_off = {5: ".sWWEWSSSSWEWWs.", 6: ".sKKKKKKKKKKKKs.", 7: "..SKGKKssKKGKS.."}
MANAVALAN = Character(
    "manavalan", "Manavalan", "Pulival Kalyanam (2003)",
    _manavalan,
    {"H": "#141010", "S": "#9a6440", "s": "#77492b", **SKIN_EYES, "M": "#5b1e1a", "L": "#7a3a2c",
     "K": "#0e0e10", "G": "#8fb9d9", "P": "#d6338a", "p": "#ffd34d", "q": "#a8236a", "C": "#f2c94c"},
    {16: ".PPPpPqqqPPpPPP.", 17: ".PPPPPPPPPPPpPP.", 18: ".PPpPqPPPPqPPpP."}, "P", "S",
    faces={
        "grin": {}, "blink": {},
        "brows": {3: "..HHHHSSSSHHHH..", 4: "..SSSSSSSSSSSS.."},
        "happy": {9: "..SSLMMMMMMLSS..", 10: "...SSLLLLLLSS..."},
        "sleep": {9: "..SSSSLMMLSSSS..", 10: "...SSSLLLLSSS..."},
        "worried": {9: "..SSSSLLLLSSSS..", 10: "...SSLSSSSLSS..."},
        "shock": {3: "..HHHHSSSSHHHH..", 4: "..SSSSSSSSSSSS..", **_shades_off,
                  9: "..SSSSMMMMSSSS..", 10: "...SSSMMMMSSS..."},
    },
    tags={"glint": {"face": "happy"}},
    signature=[("hip", "cheeks", 0, 0, -3, "glint"), ("hip", "cheeks", 0, 0, -3, "glint"),
               ("hip", "hip", -1, 0, -6), ("hip", "hip", 1, 0, 6),
               ("hip", "hip", -1, 0, -6), ("hip", "hip", 1, 0, 6)],
    backdrop=([".r.r.", "rrrrr", ".rrr.", "..r.."], {"r": "#ff5a8a"}, 3),
)

# Manoharan, owner of K & K Automobiles: side parting, thick moustache, pen in pocket, steering wheel.
_manoharan = [
    "................",
    "....HHHHHHHH....",
    "...HHHHHHHHHHH..",
    "..HHSSSSSSSHHH..",
    "..SHHHSSSSHHHS..",
    ".sSWEWSSSSWEWSs.",
    ".sSSSSSssSSSSSs.",
    "..SSSSSssSSSSS..",
    "..SSHHHHHHHHSS..",
    "..SHHHWWWWHHHS..",
    "...SSSMMMMSSS...",
    "....SSSSSSSS....",
    "......SSSS......",
    "...TTTtSStTTT...",
    ".TTTTTTttTTTTTT.",
    "TTTnTTTtTTTTTTTT",
    "TTttSSSSSSStTTTT",
    "TTTTttsssssssTTT",
    "TTTTTtTTTTtTTTTT",
]
MANOHARAN = Character(
    "manoharan", "Manoharan", "Aram + Aram = Kinnaram (1985)",
    _manoharan,
    {"H": "#151010", "S": "#a26a42", "s": "#7d4d2c", **SKIN_EYES, "M": "#55201a",
     "T": "#ece6d6", "t": "#c9c1ad", "n": "#2f6fd6"},
    {16: ".TTTTTtttTTTTTT.", 17: ".TTTTTTTTTTTTTT.", 18: ".TTTTtTTTTtTTTT."}, "T", "S",
    faces=derive_faces(_manoharan, {
        "happy": {9: "..SHHWWWWWWHHS..", 10: "...SSMMMMMMSS..."},
        "closed": {9: "..SHHHSSSSHHHS..", 10: "...SSSSSSSSSS..."},
        "flat": {9: "..SHHHSSSSHHHS..", 10: "...SSSMMMMSSS..."},
        "open": {9: "..SHHHMMMMHHHS..", 10: "...SSSMMMMSSS..."},
    }),
    tags={"wheel": {"face": "happy", "prop": Prop(
        [".kkk.", "k.k.k", "kkkkk", "k...k", ".kkk."], {"k": "#2b2b2b"}, (10, 13), "body")}},
    signature=[("chest", "chest", 0, 0, -8, "wheel"), ("chest", "chest", 0, -1, 8, "wheel"),
               ("chest", "chest", 0, 0, -8, "wheel"), ("chest", "chest", 0, -1, 8, "wheel"),
               ("chest", "chest", 0, 0, -8, "wheel"), ("chest", "chest", 0, -1, 8, "wheel")],
    backdrop=(["..cccccc..", ".cggcggcc.", "cccccccccc", "ckkcccckkc", ".kk....kk."],
              {"c": "#e7e2d2", "g": "#7aa7c7", "k": "#2a2a2a"}, 1),
)

# Aadu Thoma: Ray-Ban, red shirt, mundu with a gold kasavu border.
_thoma = [
    "....HHHHHHHH....",
    "...HHHHHHHHHH...",
    "..HHHHHHHHHHHH..",
    "..HSSSHSSSSSSH..",
    "..SHHHSSSSHHHS..",
    ".sKKKKKKKKKKKKs.",
    ".sKKGKSssSKKGKs.",
    "..SSSSSssSSSSS..",
    "..SHHHHHHHHHHS..",
    "..SSHSSSSWWHSS..",
    "...SSSSSSSSSS...",
    "....SSSSSSSS....",
    "......SSSS......",
    "...RRRrSSrRRR...",
    ".RRRRRRrrRRRRRR.",
    "RRRRRrrRrrRRRRRR",
    "RRrrSSSSSSSrRRRR",
    "RRRRrrsssssssrRR",
    "uuuuuuuuuuuuuuuu",
]
THOMA = Character(
    "thoma", "Aadu Thoma", "Spadikam (1995)",
    _thoma,
    {"H": "#120d0b", "S": "#b07a52", "s": "#8a5a37", **SKIN_EYES, "M": "#5a1d18",
     "K": "#0c0c0c", "G": "#5d6b78", "R": "#b8231f", "r": "#8c1814", "u": "#d4a63a"},
    {16: ".RRRRRrrrRRRRRR.", 17: ".RRRRRRRRRRRRRR.", 18: ".uuuuuuuuuuuuuu."}, "R", "S",
    faces={
        "grin": {}, "blink": {},
        "brows": {3: "..HHHHSSSSHHHH..", 4: "..SSSSSSSSSSSS.."},
        "happy": {9: "..SSHWWWWWWHSS..", 10: "...SSSMMMMSSS..."},
        "sleep": {9: "..SSHSSSSSSHSS..", 10: "...SSSSMMSSSS..."},
        "worried": {3: "..HSSHSSSSHSSH..", 9: "..SSHSSSSSSHSS..", 10: "...SSSMMMMSSS..."},
        "shock": {3: "..HHHHSSSSHHHH..", 4: "..SSSSSSSSSSSS..", 5: ".sWWEWSSSSWEWWs.",
                  6: ".sKKKKKKKKKKKKs.", 7: "..SKGKSssSKGKS..",
                  9: "..SSHSMMMMSHSS..", 10: "...SSSMMMMSSS..."},
    },
    tags={
        "eyes": {"rows": {5: ".sSWEWSSSSWEWSs.", 6: ".sSSSSSssSSSSSs."}},
        "mundu": {"prop": Prop(["UUUU", "UUUu", ".UUu", "..Uu"], {"U": "#f1ece0", "u": "#d4a63a"}, (-1, -3))},
    },
    signature=[("cross", "cheeks", 0, 0, 0, "eyes"), ("cross", "cheeks", 0, 0, 0, "eyes"),
               ("cross", "cheeks", 0, -1, 0), ("hip", "pump", 0, -2, -4, "mundu"),
               ("hip", "up", 0, 0, 4, "mundu"), ("hip", "pump", 0, -2, -4, "mundu"),
               ("hip", "up", 0, 0, 4, "mundu"), ("cross", "cross", 0, 0, 0)],
    backdrop=(["...kk.....", "..kRRRk...", "kkkkkkkkk.", "oo.kkk.oo.", "oo.....oo."],
              {"k": "#3a3a40", "R": "#b8231f", "o": "#6a6a70"}, 1),
)

# Mr. Bean: tweed jacket, thin red tie, one eyebrow up, Teddy in hand.
_bean = [
    "................",
    "...HHHHHHHHHH...",
    "..HHHHHHHHHHHH..",
    "..HHSSSSSSSSSH..",
    "..SHHHSSSSHHHS..",
    ".sSWEWSSSSWEWSs.",
    ".sSSSSSssSSSSSs.",
    "..SSSSssssSSSS..",
    "..SSSSSSSSSSSS..",
    "..SSSMMMMMMSSS..",
    "...SSSSSSSSSS...",
    "....SSSSSSSS....",
    "......SSSS......",
    "...JJJTRRTJJJ...",
    ".JJJJJTRRTJJJJJ.",
    "JJJJjJTRRTJjJJJJ",
    "JJjjSSSSSSSjJJJJ",
    "JJJJjjsssssssjJJ",
    "JJJJJjJJJJjJJJJJ",
]
_teddy = {"T": "#c9965e", "e": "#1a1210", "n": "#f0d3a8"}
BEAN = Character(
    "bean", "Mr. Bean", "Mr. Bean (1990)",
    _bean,
    {"H": "#4a3322", "S": "#e2b48f", "s": "#c08f6c", **SKIN_EYES, "M": "#7a2e2a",
     "J": "#7b5a3c", "j": "#5e432c", "T": "#f1ede4", "R": "#a8262a"},
    {16: ".JJJJJTRRTJJJJJ.", 17: ".JJJJJJRRJJJJJJ.", 18: ".JJJJjJJJJjJJJJ."}, "J", "S",
    faces=derive_faces(_bean, {
        "happy": {9: "..SSMMMMMMMMSS..", 10: "...SSSMMMMSSS..."},
        "closed": {9: "..SSSSMMMMSSSS.."},
        "flat": {9: "..SSSSMMMMSSSS.."},
        "open": {9: "..SSSSMMMMSSSS..", 10: "...SSSMMMMSSS..."},
    }, brows={3: "..HHSSSSSSHHHH..", 4: "..SHHHSSSSSSSS.."}),
    held=Prop(["T.T", "TTT", "TeT", "TTT"], _teddy, (0, -2)),
    tags={"hug": {"face": "happy", "prop": Prop(["T..T", "TTTT", "TeeT", "TTnT", ".TT."], _teddy, (10, 13), "body")}},
    signature=[("chest", "chest", 0, 0, -5, "hug"), ("chest", "chest", 0, -1, 5, "hug"),
               ("chest", "chest", 0, 0, -5, "hug"), ("chest", "chest", 0, -1, 5, "hug"),
               ("cross", "cross", 0, 0, 0), ("cross", "cross", 0, -1, 0)],
    backdrop=(["..gggggg..", ".gbbgbbgg.", "KKKggggggg", "gkkggggkkg", ".kk....kk."],
              {"g": "#9bd13a", "b": "#a9d6f0", "K": "#151515", "k": "#2a2a2a"}, 1),
)

# Captain Jack Sparrow: tricorn, red bandana, dreadlocks, kohl eyes, gold teeth, compass.
_jack = [
    "......AAAA......",
    "..AAAAAAAAAAAA..",
    "AAaAAAAAAAAAAaAA",
    ".HRRRRRRRRRRRRH.",
    ".HSHHHSSSSHHHSH.",
    "HHKWEKSSSSKWEKHH",
    "HhSSSSSssSSSSShH",
    "HHSSSSSssSSSSSHH",
    "hHSBBBBBBBBBBSHh",
    "HHSSBWGWWGWBSSHH",
    "hHSSSBBBBBBSSSHh",
    "HH...BBBBBB...HH",
    "hH....BSSB....Hh",
    "..VVVCCSSCCVVV..",
    ".VVVVVCCCCVVVVV.",
    "VVVVVvCCCCvVVVVV",
    "VVvvSSSSSSSvVVVV",
    "VVVVvvsssssssvVV",
    "VVVVOOOOOOOOOVVV",
]
JACK = Character(
    "jack", "Jack Sparrow", "Pirates of the Caribbean",
    _jack,
    {"H": "#2a1c12", "h": "#5a3d27", "A": "#4a2f1c", "a": "#2f1d0f", "R": "#a3262a",
     "S": "#b98458", "s": "#8e6140", **SKIN_EYES, "K": "#0b0b0b", "B": "#2a1c12", "G": "#e1b84a",
     "C": "#eee6d3", "V": "#5b3a24", "v": "#3f2817", "O": "#8c2f2a", "M": "#5a1d18"},
    {16: ".VVVVvCCCCvVVVV.", 17: ".VVVVvCCCCvVVVV.", 18: ".VVVOOOOOOOOOVV."}, "V", "S",
    faces=derive_faces(_jack, {
        "happy": {9: "HHSBWGWWGWWGBSHH"},
        "closed": {9: "HHSSBBBBBBBBSSHH"},
        "flat": {9: "HHSSBSSSSSSBSSHH"},
        "open": {9: "HHSSBSMMMMSBSSHH"},
    }, lid="K", brows={3: ".HRHHHRRRRHHHRH.", 4: ".HSSSSSSSSSSSSH."}),
    held=Prop([".GG.", "GcrG", "GccG", ".GG."], {"G": "#e1b84a", "c": "#f4eedc", "r": "#c0392b"}, (-1, -3)),
    signature=[("hip", "out", 0, 0, -4), ("hip", "out", 0, 0, -4),
               ("up", "out", -1, -1, -9), ("out", "up", 1, 0, 9),
               ("up", "out", -1, -1, -9), ("out", "up", 1, 0, 9)],
    backdrop=(["....K.....", "..KKK.K...", "..KKKKKK..", "..KKKKKK..", "bbbbbbbbbb", ".bbbbbbbb."],
              {"K": "#2e3038", "b": "#6b4a2e"}, 1),
)

# Spider-Man: webbed mask with big white lenses, red chest and the spider.
_spider = [
    "................",
    ".....RRRRRR.....",
    "...RRRkRRkRRR...",
    "..RRkRRkkRRkRR..",
    "..RkkkRkkRkkkR..",
    ".RkWWWkRRkWWWkR.",
    ".RkWWWWkkWWWWkR.",
    ".RRkWWkRRkWWkRR.",
    "..RRkkRkkRkkRR..",
    "..RkRRkRRkRRkR..",
    "...RRkRkkRkRR...",
    "....RRRkkRRR....",
    "......RRRR......",
    "...RRRRRRRRRR...",
    ".RRRRRRkkRRRRRR.",
    "URRRRkkkkkkRRRRU",
    "UUkkRRRRRRRkUUUU",
    "UUUUkkRRRRRRRkUU",
    "UUUUUkUUUUkUUUUU",
]
SPIDER = Character(
    "spider", "Spider-Man", "Marvel",
    _spider,
    {"R": "#d0202a", "k": "#141414", "W": "#f7f7f7", "U": "#2457c5", "u": "#163a8a"},
    {16: ".UURRRkkkRRRRUU.", 17: ".UURRRRkRRRRRUU.", 18: ".UUUUUUUUUUUUUU."}, "U", "R",
    faces={
        "grin": {},
        "blink": {5: ".RkkkkkRRkkkkkR.", 6: ".RkkWWkkkkWWkkR."},
        "brows": {4: "..RkWkRkkRkWkR.."},
        "happy": {7: ".RRkkkkRRkkkkRR."},
        "sleep": {5: ".RkkkkkRRkkkkkR.", 6: ".RkkkkkkkkkkkkR.", 7: ".RRkkkkRRkkkkRR."},
        "worried": {5: ".RkWWkkRRkkWWkR."},
        "shock": {4: "..RkWWkkkkWWkR..", 7: ".RkWWWWkkWWWWkR."},
    },
    signature=[("hip", "point", 0, -1, 4, "web"), ("hip", "point", 0, -1, 4, "web"),
               ("hip", "out", 0, 0, 0), ("point", "hip", 0, -1, -4, "webl"),
               ("point", "hip", 0, -1, -4, "webl"), ("out", "hip", 0, 0, 0)],
    backdrop=(["k...k", ".kkk.", "kkkkk", ".k.k."], {"k": "#5a5f6a"}, 2),
)

# Iron Man: red helmet, gold faceplate, glowing eyes and arc reactor.
_iron = [
    "................",
    ".....RRRRRR.....",
    "...RRRRRRRRRR...",
    "..RRGGGGGGGGRR..",
    "..RGGGGGGGGGGR..",
    ".rRCCCGGGGCCCRr.",
    ".rRGGGGggGGGGRr.",
    "..RGGGGggGGGGR..",
    "..RGGGGGGGGGGR..",
    "..RRGkkkkkkGRR..",
    "...RRGGGGGGRR...",
    "....RRGGGGRR....",
    "......rrrr......",
    "...RRRGRRGRRR...",
    ".RRRRRRCCRRRRRR.",
    "RRRRRrCCCCrRRRRR",
    "RRggGGGGGGGgRRRR",
    "RRRRggGGGGGGGgRR",
    "RRRRRrRRRRrRRRRR",
]
IRON = Character(
    "iron", "Iron Man", "Marvel",
    _iron,
    {"R": "#b3171f", "r": "#7f0f15", "G": "#e0b03c", "g": "#b8892a", "C": "#9ff6ff",
     "c": "#3a8fa0", "k": "#141414"},
    {16: ".RRRRRrrrRRRRRR.", 17: ".RRRGGGGGGGGRRR.", 18: ".RRRRrRRRRrRRRR."}, "R", "G",
    faces={
        "grin": {}, "brows": {}, "happy": {},
        "blink": {5: ".rRcccGGGGcccRr."},
        "sleep": {5: ".rRkkkGGGGkkkRr."},
        "worried": {5: ".rRCCkGGGGkCCRr."},
        "shock": {4: "..RCCCGGGGCCCR.."},
    },
    signature=[("hip", "out", 0, 0, 0, "blast"), ("hip", "out", 1, 0, 2, "blast"),
               ("out", "hip", 0, 0, 0, "blastl"), ("out", "hip", -1, 0, -2, "blastl"),
               ("low", "low", 0, -3, 0, "thrust"), ("low", "low", 0, -4, 0, "thrust")],
    backdrop=(["..C..", "RRGRR", ".RRR.", ".R.R.", ".C.C."],
              {"R": "#b3171f", "G": "#e0b03c", "C": "#9ff6ff"}, 1),
)

# Batman: cowl with ears, grey suit, bat in the yellow oval, cape.
_bat = [
    "...K........K...",
    "...KKKKKKKKKK...",
    "..KKKKKKKKKKKK..",
    "..KKKKKKKKKKKK..",
    "..KkkKKKKKKkkK..",
    ".KKWWWKKKKWWWKK.",
    ".KKKKKKKKKKKKKK.",
    "..KKKKSSSSKKKK..",
    "..KKKSSSSSSKKK..",
    "..KKSSSSSSSSKK..",
    "...KSSMMMMSSK...",
    "....SSSSSSSS....",
    "......KKKK......",
    "KKKGGGGGGGGGGKKK",
    "KGGGGYYYYYYGGGGK",
    "KGGGYYBBBBYYGGGK",
    "KGkkGGGGGGGkGGGK",
    "KGGGkkGGGGGGGkGK",
    "KGGGGYGYYGYGGGGK",
]
BATMAN = Character(
    "batman", "Batman", "DC",
    _bat,
    {"K": "#343b4c", "k": "#1d2230", "W": "#f4f4f4", "S": "#d8a57c", "s": "#b5845f",
     "M": "#6b2b28", "G": "#7d8590", "g": "#5d646e", "Y": "#f2c832", "B": "#111111"},
    {16: ".GGGGYBBBBYGGGG.", 17: ".GGGGGYYYYGGGGG.", 18: ".GGGYGYYYYGYGGG."}, "G", "k",
    faces={
        "grin": {}, "brows": {},
        "blink": {5: ".KKKKKKKKKKKKKK."},
        "happy": {10: "...KSSSSSMMSK..."},
        "sleep": {5: ".KKKKKKKKKKKKKK."},
        "worried": {5: ".KKKWWKKKKWWKKK."},
        "shock": {4: "..KkWWKKKKWWkK.."},
    },
    signature=[("out", "out", 0, -1, 0, "cape"), ("out", "out", 0, -2, 0, "cape"),
               ("up", "up", 0, -1, 0, "cape"), ("out", "out", 0, 0, 0, "cape"),
               ("cross", "cross", 0, 0, 0), ("cross", "cross", 0, 0, 0)],
    backdrop=(["k.....k", "kk.k.kk", ".kkkkk.", "..k.k.."], {"k": "#5b6375"}, 3),
)

# The Joker: green hair, white face, red grin, purple suit, green vest.
_joker = [
    "....NNNNNNNN....",
    "...NNNnNNNnNN...",
    "..NNNNNNNNNNNN..",
    "..NSSSSSSSSSSN..",
    "..SKKKSSSSKKKS..",
    ".sSKWEKSSKWEKSs.",
    ".sSKKKSssSKKKSs.",
    "..SSSSSssSSSSS..",
    "..RSSSSSSSSSSR..",
    "..SRRWWWWWWRRS..",
    "...SRRRRRRRRS...",
    "....SSSSSSSS....",
    "......SSSS......",
    "...PPPVOOVPPP...",
    ".PPPPPVOOVPPPPP.",
    "PPPPpPVOOVPpPPPP",
    "PPppSSSSSSSpPPPP",
    "PPPPppssssssspPP",
    "PPPPPpPPPPpPPPPP",
]
JOKER = Character(
    "joker", "The Joker", "DC",
    _joker,
    {"N": "#3fa34d", "n": "#2c7a37", "S": "#ece9e1", "s": "#c9c4b8", "K": "#3a2a48", "E": "#0b0b0b",
     "W": "#f4f0e6", "R": "#c81e2c", "M": "#4a0f16", "P": "#6b2fa0", "p": "#4b1f73",
     "V": "#3a8c4a", "O": "#e8892a"},
    {16: ".PPPPPVOOVPPPPP.", 17: ".PPPPPVVVVPPPPP.", 18: ".PPPPpPPPPpPPPP."}, "P", "S",
    faces={
        "grin": {},
        "blink": {5: ".sSKKKKSSKKKKSs."},
        "brows": {3: "..NKKKSSSSKKKN..", 4: "..SSSSSSSSSSSS.."},
        "happy": {5: ".sSKKKKSSKKKKSs.", 9: "..RRWWWWWWWWRR.."},
        "sleep": {5: ".sSKKKKSSKKKKSs.", 9: "..SRRRRRRRRRRS..", 10: "...SSSSSSSSSS..."},
        "worried": {9: "..SRRRRRRRRRRS..", 10: "...SRSSSSSSRS..."},
        "shock": {3: "..NKKKSSSSKKKN..", 4: "..SSSSSSSSSSSS..", 9: "..SRRRMMMMRRRS..", 10: "...SSRMMMMRSS..."},
    },
    tags={"haha": {"rows": {5: ".sSKKKKSSKKKKSs.", 9: "..RRWWWWWWWWRR..", 10: "...SRMMMMMMRS..."}}},
    signature=[("up", "up", 0, -1, -7, "haha"), ("pump", "pump", 0, 0, 7, "haha"),
               ("up", "up", 0, -1, -7, "haha"), ("pump", "pump", 0, 0, 7, "haha"),
               ("hip", "hip", 0, 0, 0)],
    backdrop=(["wwww", "wRRw", "wRRw", "wwRw", "wwww"], {"w": "#f2efe6", "R": "#c81e2c"}, 3),
)

# Deadpool: red mask with black eye patches, black side panels, katana.
_deadpool = [
    "................",
    ".....RRRRRR.....",
    "...RRRRRRRRRR...",
    "..RRRRRRRRRRRR..",
    "..RkkkRRRRkkkR..",
    ".RkkWkkRRkkWkkR.",
    ".RkkkkkRRkkkkkR.",
    "..RkkkRRRRkkkR..",
    "..RRRRRrrRRRRR..",
    "..RRRRRRRRRRRR..",
    "...RRRRRRRRRR...",
    "....RRRRRRRR....",
    "......kkkk......",
    "...RRRkRRkRRR...",
    ".RRRRRRkkRRRRRR.",
    "kRRRRrrRrrRRRRRk",
    "kRrrRRRRRRRrRRRk",
    "kRRRrrRRRRRRRrRk",
    "kkkkkkkGGkkkkkkk",
]
DEADPOOL = Character(
    "deadpool", "Deadpool", "Marvel",
    _deadpool,
    {"R": "#b81d24", "r": "#841318", "k": "#161616", "W": "#f4f4f4", "G": "#c9a54a"},
    {16: ".kRRRRRRRRRRRRk.", 17: ".kRRRRRRRRRRRRk.", 18: ".kkkkkkGGkkkkkk."}, "R", "r",
    faces={
        "grin": {},
        "blink": {5: ".RkkkkkRRkkkkkR."},
        "brows": {4: "..RkWkRRRRkWkR.."},
        "happy": {5: ".RkkkkkRRkkkkkR.", 4: "..RkWkRRRRkWkR.."},
        "sleep": {5: ".RkkkkkRRkkkkkR."},
        "worried": {5: ".RkWkkkRRkkkWkR."},
        "shock": {4: "..RkWkRRRRkWkR..", 5: ".RkWWWkRRkWWWkR."},
    },
    tags={"katana": {"prop": Prop(["g", "g", "g", "g", "k", "G"], {"g": "#d5dbe3", "k": "#161616", "G": "#c9a54a"}, (1, -5))}},
    signature=[("point", "point", 0, -1, 0, "pew"), ("low", "low", 0, 0, 0),
               ("point", "point", 0, -1, 0, "pew"), ("low", "low", 0, 0, 0),
               ("hip", "pump", 0, -1, -4, "katana"), ("hip", "out", 0, 0, 4, "katana")],
    backdrop=(["..yyy.", ".yGrGy", "yyyyyy"], {"y": "#e8b04a", "G": "#5bbf4a", "r": "#d83a2a"}, 2),
)

CAST = [RAMANAN, PAPPU, MANAVALAN, MANOHARAN, THOMA, BEAN, JACK, SPIDER, IRON, BATMAN, JOKER, DEADPOOL]
BY_KEY = {c.key: c for c in CAST}


def character(key):
    """The character for a settings value; unknown keys fall back to Ramanan."""
    return BY_KEY.get(key, RAMANAN)
