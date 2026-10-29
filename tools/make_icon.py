"""Draws assets/winnotch.ico (multi-size) — a dark rounded tile with a notch."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=220, fill=(28, 28, 30, 255))
d.rounded_rectangle((200, 300, S - 200, 560), radius=130, fill=(0, 0, 0, 255),
                    outline=(70, 70, 74, 255), width=10)
d.ellipse((260, 380, 360, 480), fill=(255, 45, 85, 255))           # album art dot
for i, h in enumerate((70, 130, 95, 150)):                         # visualizer bars
    x = 560 + i * 52
    d.rounded_rectangle((x, 430 - h // 2, x + 26, 430 + h // 2), radius=13, fill=(245, 245, 247, 255))
d.ellipse((480, 700, 544, 764), fill=(48, 209, 88, 255))            # "running" dot
out = Path(__file__).resolve().parents[1] / "assets" / "winnotch.ico"
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save(out.with_suffix(".png"))
print("wrote", out)
