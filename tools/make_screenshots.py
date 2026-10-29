"""Renders docs/preview.png for the README: the real notch window, built
off-screen with sample data, captured in each state. No services start and
the mouse isn't touched.

    python tools/make_screenshots.py
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_SCALE_FACTOR", "1.6")  # render at high resolution

from PySide6.QtCore import QBuffer, QEventLoop, QIODevice, QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from notch.bus import Bus  # noqa: E402
from notch.settings import DEFAULTS, Settings  # noqa: E402
from notch.ui.window import NotchWindow  # noqa: E402

OUT = ROOT / "docs"


class SampleSettings(Settings):
    """Default settings held in memory, so your own settings don't leak in."""

    def __init__(self):
        super().__init__()
        self._values = dict(DEFAULTS)

    def get(self, key):
        return self._values[key]

    def set(self, key, value):
        if self._values.get(key) != value:
            self._values[key] = value
            self.changed.emit(key)


class Stub:
    level = 0.55
    device_name = "Speakers (Realtek Audio)"

    def command(self, *_):
        pass

    def fetch(self, *_):
        pass


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def cover_art():
    img = QImage(300, 300, QImage.Format_ARGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 300, 300)
    g.setColorAt(0, QColor("#f3c51b"))
    g.setColorAt(1, QColor("#e0336b"))
    p.fillRect(img.rect(), g)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 70))
    for i, (x, y, r) in enumerate(((70, 80, 40), (210, 150, 60), (120, 230, 30))):
        p.drawEllipse(QPointF(x, y), r, r)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def capture(win):
    """The notch surface as an image (transparent around the shape)."""
    return win.grab(win.surface.geometry()).toImage()


def main():
    app = QApplication(sys.argv)
    win = NotchWindow(Bus(), Stub(), Stub(), Stub(), SampleSettings())
    win.show()
    win.move(-6000, -6000)  # off-screen: nothing appears on your desktop
    wait(300)
    win.on_battery(82, True)
    win.on_battery(82, True)

    shots = {}
    win._set_mode("idle")
    wait(900)
    shots["idle"] = capture(win)

    snap = {"active": True, "key": ("demo", "Changa Chaka", "Ramanan"), "app": "Spotify",
            "title": "Changa Chaka Chakaa", "artist": "Ramanan & the Fish", "album": "Punjabi House Grooves",
            "playing": True, "position": 74.0, "duration": 212.0, "updated_at": time.time(),
            "can_seek": True, "can_next": True, "can_prev": True, "art": cover_art()}
    win.on_media(snap)
    wait(900)
    shots["compact"] = capture(win)

    win.on_volume(0.64, False)
    wait(700)
    shots["hud"] = capture(win)
    win._hud_done()

    win.holds += 1  # keep it open: the cursor isn't over the off-screen window
    win.open(0)
    win.expanded_view.media.setLyrics([(0, "Mothalaalee… changa chaka chakaa ♪")])
    wait(1000)
    shots["expanded"] = capture(win)
    win.holds -= 1
    win.expanded = False

    win.media = {"active": False}
    win.edge = "float"
    win._anchor = (win.width() / 2, win.height() / 2)
    win._apply_idle_style()
    win._resolve()
    win._reshape()
    wait(900)
    shots["float"] = capture(win)

    OUT.mkdir(exist_ok=True)
    compose(shots).save(str(OUT / "preview.png"))
    print("wrote", OUT / "preview.png")


def compose(shots):
    dpr = shots["expanded"].devicePixelRatio()
    W, gap, pad = 1200, 24, 40
    small_w = (W - 2 * pad - gap) / 2
    hero_h, small_h = 290, 200
    H = pad + hero_h + gap + 2 * (small_h + gap) + pad - gap

    canvas = QImage(int(W * dpr), int(H * dpr), QImage.Format_ARGB32)
    canvas.setDevicePixelRatio(dpr)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, 0, H)
    bg.setColorAt(0, QColor("#2f6f7c"))
    bg.setColorAt(1, QColor("#16363e"))
    p.fillRect(QRectF(0, 0, W, H), bg)

    def tile(rect, shot, title, subtitle, floating=False):
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)
        p.save()
        p.setClipPath(path)
        p.fillRect(rect, QColor(255, 255, 255, 18))
        sw = shot.width() / dpr
        sh = shot.height() / dpr
        x = rect.center().x() - sw / 2
        y = rect.top() + (rect.height() - 70 - sh) / 2 + 8 if floating else rect.top()
        p.drawImage(QRectF(x, y, sw, sh), shot)
        p.restore()
        p.setPen(QColor("#f5f5f7"))
        f = QFont()
        f.setFamilies(["Segoe UI Variable Display", "Segoe UI"])
        f.setPixelSize(19)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(rect.left() + 24, rect.bottom() - 62, rect.width() - 48, 26),
                   Qt.AlignLeft | Qt.AlignVCenter, title)
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor("#b9d3d8"))
        p.drawText(QRectF(rect.left() + 24, rect.bottom() - 36, rect.width() - 48, 22),
                   Qt.AlignLeft | Qt.AlignVCenter, subtitle)

    y = pad
    tile(QRectF(pad, y, W - 2 * pad, hero_h), shots["expanded"], "Hover to expand",
         "Now playing with synced lyrics, seek, ±15 s and output switching · file shelf · mirror")
    y += hero_h + gap
    tile(QRectF(pad, y, small_w, small_h), shots["idle"], "Ramanan lives in your notch",
         "He blinks, raises his brows and fish swim past")
    tile(QRectF(pad + small_w + gap, y, small_w, small_h), shots["compact"], "…and dances to your music",
         "Now-playing pill with live visualizer")
    y += small_h + gap
    tile(QRectF(pad, y, small_w, small_h), shots["hud"], "System HUDs",
         "Volume, brightness, Caps Lock, DND, battery, camera/mic, downloads")
    tile(QRectF(pad + small_w + gap, y, small_w, small_h), shots["float"], "Drag it anywhere",
         "Dock to any screen edge, or float as a pill", floating=True)
    p.end()
    return canvas


if __name__ == "__main__":
    main()
