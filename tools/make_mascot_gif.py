"""Renders every Ramanan dance move and mood into one animated GIF.
Usage: python tools/make_mascot_gif.py [out.gif]"""

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
from notch.ui import mascot  # noqa: E402

ZOOM = 4          # on top of the sprite's own 2x, so 8 screen px per sprite pixel
FPS = 15
SECONDS = 8
TILE_W, TILE_H, LABEL_H = 220, 170, 30
COLS = 5
TILES = [(f"dance: {m}", "dance", m) for m in mascot.MOVES] + [
    ("party (download / charge done)", "party", None), ("shock (camera on)", "shock", None),
    ("sweat (low battery)", "sweat", None), ("sleep (idle 2 min)", "sleep", None)]

clock = [1000.0]
mascot.time = types.SimpleNamespace(monotonic=lambda: clock[0])


def make_actor(state, move):
    mood = mascot.Mood()
    level = 0.1 if move in mascot.CALM_MOVES else 0.6
    r = mascot.Ramanan(lambda: (level, state == "dance"), mood)
    if move:
        r._move, r._move_until, r._energy = move, 10 ** 9, level
    if state == "party":
        mood._party_until = float("inf")
    elif state == "sweat":
        mood._low_battery = True
    elif state == "sleep":
        mood._idle, mood._idle_checked = 999, float("inf")
    return r, level


def render(r, level, now):
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
    return small.scaled(small.width() * ZOOM, small.height() * ZOOM)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "mascot_moves.gif")
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    actors = [(label, state, *make_actor(state, move)) for label, state, move in TILES]
    rows = math.ceil(len(TILES) / COLS)
    start = clock[0]
    frames = []
    for i in range(FPS * SECONDS):
        t = i / FPS
        clock[0] = now = start + t
        sheet = QImage(COLS * TILE_W, rows * (TILE_H + LABEL_H), QImage.Format_RGB32)
        sheet.fill(QColor("#111114"))
        p = QPainter(sheet)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont("Segoe UI", 10))
        for n, (label, state, r, level) in enumerate(actors):
            if state == "shock":  # replay the reaction every 3 seconds
                r.mood._shock_until = now - (t % 3) + r.mood.SHOCK_FOR
            x, y = (n % COLS) * TILE_W, (n // COLS) * (TILE_H + LABEL_H)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#000000"))
            p.drawRoundedRect(QRectF(x + 10, y + 10, TILE_W - 20, TILE_H - 10), 26, 26)
            sprite = render(r, level, now)
            p.drawImage(x + (TILE_W - sprite.width()) // 2, y + TILE_H - sprite.height(), sprite)
            p.setPen(QColor("#d8d8dc"))
            p.drawText(QRectF(x, y + TILE_H, TILE_W, LABEL_H), Qt.AlignCenter, label)
        p.end()
        buf = QBuffer()
        buf.open(QBuffer.ReadWrite)
        sheet.save(buf, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("P", palette=Image.ADAPTIVE))
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
    print(f"wrote {out} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
