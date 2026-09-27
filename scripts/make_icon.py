"""Create the macOS icon from the user-supplied portrait bundled with the app."""

from pathlib import Path
import subprocess
import tempfile

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath

assets = Path(__file__).resolve().parents[1] / "src/free_agent/desktop/assets"
portrait = QImage(str(assets / "portrait.png"))
if portrait.isNull():
    raise SystemExit("Could not load portrait.png")

# A square head-and-book crop remains legible at Dock and Finder icon sizes.
crop = portrait.copy(QRect(0, 0, portrait.width(), portrait.width()))
logo = crop.scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio,
                   Qt.TransformationMode.SmoothTransformation)
if not logo.save(str(assets / "logo.png")):
    raise SystemExit("Could not save logo.png")
icon = QImage(1024, 1024, QImage.Format.Format_ARGB32)
icon.fill(Qt.GlobalColor.transparent)
painter = QPainter(icon)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
tile = QPainterPath()
tile.addRoundedRect(QRectF(100, 100, 824, 824), 184, 184)
painter.fillPath(tile, QColor("#f2e9da"))
painter.setClipPath(tile)
painter.drawImage(QRect(116, 116, 792, 792), crop)
painter.end()
if not icon.save(str(assets / "app-icon.png")):
    raise SystemExit("Could not save app-icon.png")

with tempfile.TemporaryDirectory() as temporary:
    iconset = Path(temporary) / "NokiAI.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pixels = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            resized = icon.scaled(pixels, pixels, Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            if not resized.save(str(iconset / name)):
                raise SystemExit(f"Could not save {name}")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(assets / "NokiAI.icns")],
                   check=True)
