from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = QColor(0, 0, 0)
FG = QColor(245, 245, 247)
SUB = QColor(152, 152, 157)
TRACK = QColor(255, 255, 255, 38)
HOVER = QColor(255, 255, 255, 28)
GREEN = QColor("#30d158")
ORANGE = QColor("#ff9f0a")
RED = QColor("#ff453a")
BLUE = QColor("#0a84ff")
PURPLE = QColor("#bf5af2")
YELLOW = QColor("#ffd60a")


class G:
    """Segoe Fluent Icons / Segoe MDL2 Assets code points."""
    VOLUME = ("", "", "", "")
    MUTE = ""
    BRIGHTNESS = ""
    KEYBOARD = ""
    MOON = ""
    VIDEO = ""
    CAMERA = ""
    MIC = ""
    DOWNLOAD = ""
    CHECK = ""
    PLAY = ""
    PAUSE = ""
    PREV = ""
    NEXT = ""
    REWIND = ""
    FORWARD = ""
    SPEAKER = ""
    MUSIC = ""
    FOLDER = ""
    HOME = ""
    SETTINGS = ""
    DELETE = ""
    BOLT = ""
    WARNING = ""


_icon_family = None


def icon_font(px):
    global _icon_family
    if _icon_family is None:
        families = set(QFontDatabase.families())
        _icon_family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families),
                            "Segoe UI Symbol")
    f = QFont(_icon_family)
    f.setPixelSize(px)
    return f


def text_font(px, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


MENU_STYLE = """
QMenu { background: #1c1c1e; color: #f5f5f7; border: 1px solid #3a3a3c;
        border-radius: 10px; padding: 6px; font: 13px 'Segoe UI'; }
QMenu::item { padding: 6px 22px 6px 26px; border-radius: 6px; }
QMenu::item:selected { background: #0a84ff; }
QMenu::item:disabled { color: #8e8e93; }
QMenu::separator { height: 1px; background: #3a3a3c; margin: 5px 8px; }
QMenu::indicator { width: 14px; left: 6px; }
"""
