"""Assemble des captures en planches, une zone recadree par image, legendee.

    python contact_sheet.py --frames out --crop 720,95,580,150 --pattern "rec_*.png"

Les images identiques une fois recadrees ne sont gardees qu'une fois : ce qui
reste, c'est la suite des etats visibles de la zone, image intermediaire
comprise.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True)
    parser.add_argument("--crop", help="x,y,largeur,hauteur dans chaque image.")
    parser.add_argument("--pattern", default="rec_*.png")
    parser.add_argument("--per-sheet", type=int, default=12)
    args = parser.parse_args()

    from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

    app = QGuiApplication([])  # drawText exige une application Qt
    folder = Path(args.frames)
    crops, previous = [], None
    for path in sorted(folder.glob(args.pattern)):
        image = QImage(str(path))
        if args.crop:
            image = image.copy(*(int(v) for v in args.crop.split(",")))
        key = bytes(image.constBits())
        if key != previous:
            crops.append((path.name, image))
            previous = key
    if not crops:
        print("no frames")
        return 1
    width = max(image.width() for _, image in crops)
    sheets = [crops[i:i + args.per_sheet] for i in range(0, len(crops), args.per_sheet)]
    for number, chunk in enumerate(sheets):
        sheet = QImage(width, sum(image.height() + 18 for _, image in chunk),
                       QImage.Format_RGB32)
        sheet.fill(QColor("white"))
        painter = QPainter(sheet)
        y = 0
        for name, image in chunk:
            painter.setPen(QColor("black"))
            painter.drawText(4, y + 13, name)
            painter.drawImage(0, y + 16, image)
            y += image.height() + 18
        painter.end()
        sheet.save(str(folder / f"sheet_{number}.png"))
    print(f"{len(crops)} distinct frames -> {len(sheets)} sheet(s) in {folder}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
