"""Previews the whole cast: one animated GIF per character (idle, signature,
every dance move and mood), an overview GIF of everyone, and a still sheet of
every face and signature frame.
Usage: python tools/make_cast_gif.py [out_dir] [--sheet-only]"""

import io
import math
import sys
import types
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notch.ui import cast, mascot  # noqa: E402

ZOOM = 4          # on top of the sprite's own 2x
FPS = 15
SECONDS = 8
TILE_W, TILE_H, LABEL_H = 220, 170, 30
COLS = 4
BG, TILE_BG, TEXT = "#111114", "#000000", "#d8d8dc"
FACES = ("grin", "blink", "brows", "happy", "worried", "shock", "sleep")

clock = [1000.0]
mascot.time = cast.time = types.SimpleNamespace(monotonic=lambda: clock[0])


def tiles_for(char):
    tiles = [("idle", "idle", None)]
    if char.signature:
        tiles.append(("signature", "signature", None))
    tiles += [(f"dance: {m}", "dance", m) for m in mascot.MOVES]
    tiles += [("party", "party", None), ("shock (camera on)", "shock", None),
              ("sweat (low battery)", "sweat", None), ("sleep (idle)", "sleep", None)]
    return tiles


def make_actor(char, state, move):
    mood = mascot.Mood()
    level = 0.1 if move in mascot.CALM_MOVES else 0.6
    r = cast.CastMember(char, lambda: (level, state == "dance"), mood)
    r._quirk_at = float("inf")
    if move:
        r._move, r._move_until, r._energy = move, 10 ** 9, level
    if state == "party":
        mood._party_until = float("inf")
    elif state == "sweat":
        mood._low_battery = True
    elif state == "sleep":
        mood._idle, mood._idle_checked = 999, float("inf")
    return r, level


def render(r, level, now, zoom=ZOOM):
    """Same drawing as Ramanan.paintEvent, into an image, then zoomed."""
    img, dx, dy, tilt, fx = r.pose(now, level, r.source()[1])
    img = r.effects(img, fx, now)
    small = QImage(r.width(), r.height(), QImage.Format_ARGB32)
    small.fill(Qt.transparent)
    p = QPainter(small)
    p.translate(r.width() / 2, r.height())
    p.rotate(tilt)
    p.translate(-r.width() / 2 + dx * r.PIXEL, -r.height() + dy)
    p.drawImage(QRectF(0, 0, r.width(), r.height()), img)
    p.end()
    return small.scaled(small.width() * zoom, small.height() * zoom)


def to_pil(qimg):
    buf = QBuffer()
    buf.open(QBuffer.ReadWrite)
    qimg.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data())))


def draw_backdrop(p, char, x, y, w, h, t):
    if not char.backdrop:
        return
    rows, colors, count = char.backdrop
    img = mascot._render(rows, colors)
    s = 2 * ZOOM // 2
    for i in range(count):
        span = w + img.width() * s
        bx = x + w - ((t * 28 + i * span / count) % span)
        by = y + 18 + (i * 34) % max(1, h - img.height() * s - 30)
        p.drawImage(QRectF(round(bx), by, img.width() * s, img.height() * s), img)


def gif(path, actors, char_of, cols):
    rows = math.ceil(len(actors) / cols)
    start = clock[0]
    frames = []
    for i in range(FPS * SECONDS):
        t = i / FPS
        clock[0] = now = start + t
        sheet = QImage(cols * TILE_W, rows * (TILE_H + LABEL_H), QImage.Format_RGB32)
        sheet.fill(QColor(BG))
        p = QPainter(sheet)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont("Segoe UI", 10))
        for n, (label, state, r, level) in enumerate(actors):
            if state == "shock":  # replay the reaction every 3 seconds
                r.mood._shock_until = now - (t % 3) + r.mood.SHOCK_FOR
            if state == "signature":  # loop the signature action back to back
                length = len(r.char.signature) / mascot.BEATS_PER_SECOND + 0.6
                r._quirk_at = now - (t % length)
            x, y = (n % cols) * TILE_W, (n // cols) * (TILE_H + LABEL_H)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(TILE_BG))
            p.drawRoundedRect(QRectF(x + 10, y + 10, TILE_W - 20, TILE_H - 10), 26, 26)
            if state == "idle":
                p.save()
                p.setClipRect(QRectF(x + 10, y + 10, TILE_W - 20, TILE_H - 10))
                draw_backdrop(p, char_of(n), x + 10, y + 10, TILE_W - 20, TILE_H - 10, t)
                p.restore()
            sprite = render(r, level, now)
            p.drawImage(x + (TILE_W - sprite.width()) // 2, y + TILE_H - sprite.height(), sprite)
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(x, y + TILE_H, TILE_W, LABEL_H), Qt.AlignCenter, label)
        p.end()
        frames.append(to_pil(sheet).convert("P", palette=Image.ADAPTIVE))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
    print(f"wrote {path}")


def still_sheet(path):
    """Every face plus every signature frame, one character per row."""
    z = 6
    cell_w, cell_h = mascot.W * z + 12, mascot.H * z + 12
    cols = len(FACES) + max(len(c.signature) for c in cast.CAST)
    name_w = 170
    sheet = QImage(name_w + cols * cell_w, len(cast.CAST) * cell_h, QImage.Format_RGB32)
    sheet.fill(QColor(TILE_BG))
    p = QPainter(sheet)
    p.setFont(QFont("Segoe UI", 10))
    for row, char in enumerate(cast.CAST):
        y = row * cell_h
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(6, y, name_w, cell_h), Qt.AlignVCenter, char.name)
        frames = [cast.compose(char, f) for f in FACES]
        frames += [cast.compose(char, "grin", s[0], s[1], (*s, None)[5]) for s in char.signature]
        for col, img in enumerate(frames):
            p.drawImage(QRectF(name_w + col * cell_w + 6, y + 6, mascot.W * z, mascot.H * z), img)
    p.end()
    sheet.save(str(path))
    print(f"wrote {path}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0] if args else "cast_preview")
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    still_sheet(out / "faces_sheet.png")
    if "--sheet-only" in sys.argv:
        return
    for char in cast.CAST:
        actors = [(label, state, *make_actor(char, state, move)) for label, state, move in tiles_for(char)]
        gif(out / f"{char.key}.gif", actors, lambda n, c=char: c, COLS)
    everyone = []
    for char in cast.CAST:
        state = "signature" if char.signature else "idle"
        everyone.append((char.name, state, *make_actor(char, state, None)))
    gif(out / "_everyone.gif", everyone, lambda n: cast.CAST[n], 6)


if __name__ == "__main__":
    main()
