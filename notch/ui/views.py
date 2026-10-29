"""Content shown inside the notch when it is not expanded."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .mascot import MascotScene, Ramanan
from .theme import FG, SUB
from .widgets import AlbumArt, Bar, IconSlot, PrivacyDots, TextLabel, Visualizer


class IdleView(QWidget):
    def __init__(self, level_source, parent=None):
        super().__init__(parent)
        self.scene = MascotScene(level_source, self)
        self.scene.hide()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 14, 0)
        lay.addStretch()
        self.dots = PrivacyDots()
        lay.addWidget(self.dots)

    def setMascot(self, on):
        self.scene.setVisible(on)
        self.scene.lower()

    def resizeEvent(self, _):
        self.scene.setGeometry(self.rect())


class CompactView(QWidget):
    """Dynamic-Island style 'now playing': artwork (or the dancing mascot)
    left, bars right."""

    def __init__(self, level_source, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 14, 0)
        lay.setSpacing(10)
        self.ramanan = Ramanan(level_source)
        self.ramanan.hide()
        self.art = AlbumArt(22, 6)
        self.title = TextLabel(12, QFont.Weight.Medium, SUB)
        self.dots = PrivacyDots()
        self.viz = Visualizer(4, 3, 2, level_source)
        lay.addWidget(self.ramanan, 0, Qt.AlignBottom)
        lay.addWidget(self.art)
        lay.addWidget(self.title, 1)
        lay.addWidget(self.dots)
        lay.addWidget(self.viz)

    def setMascot(self, on):
        self.ramanan.setVisible(on)
        self.art.setVisible(not on)

    def setMedia(self, snap, image, accent):
        self.art.setImage(image)
        self.title.setText(snap.get("title", ""))
        self.viz.setColor(accent)


class HudView(QWidget):
    """Icon + title/subtitle + optional bar + value. Used for system HUDs
    (volume, brightness, Caps Lock, ...) and live activities (downloads)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 18, 0)
        lay.setSpacing(12)
        self.icon = IconSlot()
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addStretch()
        self.title = TextLabel(13, QFont.Weight.DemiBold)
        self.subtitle = TextLabel(11, color=SUB)
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        texts.addStretch()
        self.bar = Bar(5)
        self.bar.setFixedWidth(104)
        self.value = TextLabel(13, QFont.Weight.DemiBold, align=Qt.AlignRight)
        self.value.setFixedWidth(46)
        lay.addWidget(self.icon)
        lay.addLayout(texts, 1)
        lay.addWidget(self.bar)
        lay.addWidget(self.value)

    def setSpec(self, spec):
        self.icon.setSpec(spec["icon"], spec.get("animate", False))
        self.title.setText(spec.get("title", ""))
        subtitle = spec.get("subtitle", "")
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        bar = spec.get("bar")
        self.bar.setVisible(bar is not None)
        if bar == "indeterminate":
            self.bar.setIndeterminate(True)
        else:
            self.bar.setIndeterminate(False)
            self.bar.setValue(bar or 0.0)
        self.bar.setColor(spec.get("color", FG))
        value = spec.get("value", "")
        self.value.setText(value)
        self.value.setColor(spec.get("value_color", FG))
        self.value.setVisible(bool(value))
