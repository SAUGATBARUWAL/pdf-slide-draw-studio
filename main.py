# main.py

import os
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QPalette

from main_window import MainWindow, STYLESHEET


os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--no-sandbox"
)


def main():

    app = QApplication(
        sys.argv
    )

    # Global palette
    palette = QPalette()

    palette.setColor(
        QPalette.ColorRole.Window,
        QColor("#12121f")
    )

    palette.setColor(
        QPalette.ColorRole.WindowText,
        QColor("#e0e0ff")
    )

    palette.setColor(
        QPalette.ColorRole.Base,
        QColor("#1e1e3a")
    )

    palette.setColor(
        QPalette.ColorRole.Text,
        QColor("#e0e0ff")
    )

    palette.setColor(
        QPalette.ColorRole.Button,
        QColor("#1e1e3a")
    )

    palette.setColor(
        QPalette.ColorRole.ButtonText,
        QColor("#e0e0ff")
    )

    palette.setColor(
        QPalette.ColorRole.Highlight,
        QColor("#3a5bbf")
    )

    app.setPalette(
        palette
    )

    # Global stylesheet
    app.setStyleSheet(
        STYLESHEET
    )

    # Main window
    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()