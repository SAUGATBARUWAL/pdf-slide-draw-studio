# main_window.py

from __future__ import annotations

import os
import sys
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QStackedWidget,
)

from config import DOCUMENTS_DIR

from home import HomeSection
from canvas import CanvasSection
from sketch import SketchSection
from documents import DocumentSection
from summarizer import SummarizerSection


# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL APPLICATION STYLESHEET
# ──────────────────────────────────────────────────────────────────────────────

STYLESHEET = """

/* ═══════════════════════════════════════════════════════════════════════════
   GLOBAL
   ═══════════════════════════════════════════════════════════════════════════ */

QMainWindow {
    background: #12121f;
}

QWidget {
    color: #e0e0ff;
    font-family: Arial, sans-serif;
    font-size: 12px;
}

QLabel {
    color: #e0e0ff;
}

QLineEdit {
    background: #1e1e3a;
    color: #e0e0ff;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #3a5bbf;
}

QLineEdit:focus {
    border: 1px solid #3b82f6;
}


/* ═══════════════════════════════════════════════════════════════════════════
   SIDEBAR
   ═══════════════════════════════════════════════════════════════════════════ */

QWidget#sidebar {
    background: #0f172a;
    border-right: 1px solid #1e293b;
}

QLabel#sidebar_title {
    color: #e0e0ff;
    font-size: 24px;
    font-weight: bold;
    line-height: 28px;
}


/* Navigation buttons */

QPushButton#nav_btn {
    background: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 8px;
    text-align: left;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: bold;
}

QPushButton#nav_btn:hover {
    background: #1e293b;
    color: #ffffff;
}

QPushButton#nav_btn:checked {
    background: #263449;
    color: #ffffff;
    border-left: 3px solid #3b82f6;
}


/* Folder button */

QPushButton#folder_btn {
    background: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 5px 8px;
    font-size: 10px;
}

QPushButton#folder_btn:hover {
    background: #263449;
    color: #ffffff;
}


/* ═══════════════════════════════════════════════════════════════════════════
   GENERIC BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

QPushButton#action_btn {
    background: #263449;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 5px 10px;
    font-weight: bold;
}

QPushButton#action_btn:hover {
    background: #334155;
    color: #ffffff;
}

QPushButton#action_btn:pressed {
    background: #1e293b;
}

QPushButton#action_btn:disabled {
    background: #1e293b;
    color: #64748b;
}


/* Danger */

QPushButton#danger_btn {
    background: #7f1d1d;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 5px 10px;
    font-weight: bold;
}

QPushButton#danger_btn:hover {
    background: #991b1b;
}

QPushButton#danger_btn:pressed {
    background: #681414;
}


/* Green */

QPushButton#green_btn {
    background: #166534;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 5px 10px;
    font-weight: bold;
}

QPushButton#green_btn:hover {
    background: #15803d;
}


/* Blue */

QPushButton#blue_btn {
    background: #1d4ed8;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 5px 12px;
    font-weight: bold;
}

QPushButton#blue_btn:hover {
    background: #2563eb;
}

QPushButton#blue_btn:disabled {
    background: #1e3a8a;
    color: #94a3b8;
}


/* ═══════════════════════════════════════════════════════════════════════════
   CARDS / TOOLBARS
   ═══════════════════════════════════════════════════════════════════════════ */

QFrame#card {
    background: #171827;
    border: 1px solid #252a3b;
    border-radius: 12px;
}

QFrame#toolbar_card {
    background: #151827;
    border-bottom: 1px solid #252a3b;
}

QFrame#present_bar {
    background: #151827;
    border: 1px solid #252a3b;
    border-radius: 8px;
}


/* ═══════════════════════════════════════════════════════════════════════════
   DOCUMENT FOLDER BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

QPushButton#folder_item {
    background: #1a1e2a;
    color: #cbd5e1;
    border: 1px solid #1e293b;
    border-radius: 7px;
    text-align: left;
    padding: 4px 10px;
    font-size: 11px;
}

QPushButton#folder_item:hover {
    background: #263449;
    border: 1px solid #334155;
    color: #ffffff;
}

QPushButton#folder_item[selected="true"] {
    background: #1e3a5f;
    border: 1px solid #3b82f6;
    color: #ffffff;
}


/* ═══════════════════════════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════════════════════════ */

QScrollBar:vertical {
    background: #0f172a;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #334155;
    min-height: 30px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #475569;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #0f172a;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #334155;
    min-width: 30px;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #475569;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}


/* ═══════════════════════════════════════════════════════════════════════════
   TAB WIDGET
   ═══════════════════════════════════════════════════════════════════════════ */

QTabWidget::pane {
    border: 1px solid #1e2230;
    background: #12121f;
    border-radius: 8px;
}

QTabBar::tab {
    background: #1a1e2a;
    color: #8888aa;
    border: 1px solid #1e2230;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    padding: 6px 18px;
    font-size: 12px;
    font-weight: bold;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #1e293b;
    color: #e0e0ff;
    border-bottom: 2px solid #3b82f6;
}

QTabBar::tab:hover {
    background: #1e293b;
    color: #ffffff;
}


/* ═══════════════════════════════════════════════════════════════════════════
   SLIDERS
   ═══════════════════════════════════════════════════════════════════════════ */

QSlider::groove:horizontal {
    height: 5px;
    background: #334155;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    width: 13px;
    margin: -4px 0;
    background: #3b82f6;
    border-radius: 6px;
}

QSlider::handle:horizontal:hover {
    background: #60a5fa;
}


/* ═══════════════════════════════════════════════════════════════════════════
   SPLITTERS
   ═══════════════════════════════════════════════════════════════════════════ */

QSplitter::handle {
    background: #1e293b;
}

QSplitter::handle:hover {
    background: #334155;
}


/* ═══════════════════════════════════════════════════════════════════════════
   TEXT EDIT
   ═══════════════════════════════════════════════════════════════════════════ */

QTextEdit {
    background: #161925;
    color: #e2e8f0;
    border: 1px solid #273047;
    border-radius: 8px;
    padding: 8px;
}

"""


# ──────────────────────────────────────────────────────────────────────────────
# MAIN WINDOW
# ──────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "PDF Slide & Draw Studio"
        )

        self.resize(
            1060,
            700
        )

        self.setMinimumSize(
            800,
            520
        )

        # ──────────────────────────────────────────────────────────────
        # Central widget
        # ──────────────────────────────────────────────────────────────

        central = QWidget()

        self.setCentralWidget(
            central
        )

        root = QHBoxLayout(
            central
        )

        root.setContentsMargins(
            0,
            0,
            0,
            0
        )

        root.setSpacing(0)

        # ──────────────────────────────────────────────────────────────
        # Build application
        # ──────────────────────────────────────────────────────────────

        self._build_sidebar(
            root
        )

        self._build_content(
            root
        )

        # Start on Home
        self._nav(
            "home"
        )

    # =========================================================================
    # SIDEBAR
    # =========================================================================

    def _build_sidebar(
        self,
        root,
    ):

        sidebar = QWidget()

        sidebar.setObjectName(
            "sidebar"
        )

        sidebar.setFixedWidth(
            210
        )

        sidebar_layout = QVBoxLayout(
            sidebar
        )

        sidebar_layout.setContentsMargins(
            12,
            28,
            12,
            20
        )

        sidebar_layout.setSpacing(
            4
        )

        # ──────────────────────────────────────────────────────────────
        # Title
        # ──────────────────────────────────────────────────────────────

        title = QLabel(
            "PDF\nStudio"
        )

        title.setObjectName(
            "sidebar_title"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        sidebar_layout.addWidget(
            title
        )

        sidebar_layout.addSpacing(
            20
        )

        # ──────────────────────────────────────────────────────────────
        # Navigation
        # ──────────────────────────────────────────────────────────────

        self._nav_btns = {}

        navigation = [
            ("🏠  Home", "home"),
            ("🎨  Canvas", "canvas"),
            ("✏️  Sketch", "sketch"),
            ("📄  Documents", "documents"),
            ("✦  Summarizer", "summarizer"),
        ]

        for label, key in navigation:

            button = QPushButton(
                label
            )

            button.setObjectName(
                "nav_btn"
            )

            button.setCheckable(
                True
            )

            button.setFixedHeight(
                42
            )

            # IMPORTANT:
            # key=key prevents the lambda from using
            # the last loop value.
            button.clicked.connect(
                lambda _,
                k=key:
                self._nav(k)
            )

            sidebar_layout.addWidget(
                button
            )

            self._nav_btns[
                key
            ] = button

        sidebar_layout.addStretch()

        # ──────────────────────────────────────────────────────────────
        # Open documents folder
        # ──────────────────────────────────────────────────────────────

        open_btn = QPushButton(
            "📁 Open documents folder"
        )

        open_btn.setObjectName(
            "folder_btn"
        )

        open_btn.setFixedHeight(
            34
        )

        open_btn.clicked.connect(
            self._open_docs_dir
        )

        sidebar_layout.addWidget(
            open_btn
        )

        root.addWidget(
            sidebar
        )

    # =========================================================================
    # OPEN DOCUMENTS FOLDER
    # =========================================================================

    def _open_docs_dir(self):

        DOCUMENTS_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        try:

            if sys.platform == "win32":

                os.startfile(
                    DOCUMENTS_DIR
                )

            elif sys.platform == "darwin":

                subprocess.Popen(
                    [
                        "open",
                        str(DOCUMENTS_DIR)
                    ]
                )

            else:

                subprocess.Popen(
                    [
                        "xdg-open",
                        str(DOCUMENTS_DIR)
                    ]
                )

        except Exception as e:

            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                "Cannot open folder",
                str(e)
            )

    # =========================================================================
    # CONTENT STACK
    # =========================================================================

    def _build_content(
        self,
        root,
    ):

        self._stack = QStackedWidget()

        # ──────────────────────────────────────────────────────────────
        # Create sections
        # ──────────────────────────────────────────────────────────────

        self._home_sec = HomeSection()

        self._canvas_sec = CanvasSection()

        self._sketch_sec = SketchSection()

        self._doc_sec = DocumentSection()

        self._summ_sec = SummarizerSection()

        # ──────────────────────────────────────────────────────────────
        # Home → Documents synchronization
        # ──────────────────────────────────────────────────────────────

        self._home_sec.folder_changed.connect(
            self._doc_sec._refresh_folders
        )

        # ──────────────────────────────────────────────────────────────
        # Add sections to stack
        # ──────────────────────────────────────────────────────────────

        self._smap = {}

        sections = [
            (
                "home",
                self._home_sec
            ),
            (
                "canvas",
                self._canvas_sec
            ),
            (
                "sketch",
                self._sketch_sec
            ),
            (
                "documents",
                self._doc_sec
            ),
            (
                "summarizer",
                self._summ_sec
            ),
        ]

        for key, widget in sections:

            index = self._stack.addWidget(
                widget
            )

            self._smap[
                key
            ] = (
                widget,
                index
            )

        root.addWidget(
            self._stack,
            stretch=1
        )

    # =========================================================================
    # NAVIGATION
    # =========================================================================

    def _nav(
        self,
        key: str,
    ):

        if key not in self._smap:
            return

        # -------------------------------------------------------------
        # Update sidebar selection
        # -------------------------------------------------------------

        for nav_key, button in (
            self._nav_btns.items()
        ):

            button.setChecked(
                nav_key == key
            )

        # -------------------------------------------------------------
        # Switch stack
        # -------------------------------------------------------------

        _, index = self._smap[
            key
        ]

        self._stack.setCurrentIndex(
            index
        )

        # -------------------------------------------------------------
        # Summarizer
        # -------------------------------------------------------------

        if key == "summarizer":

            self._summ_sec.boot()

        # -------------------------------------------------------------
        # Home refresh
        # -------------------------------------------------------------

        elif key == "home":

            self._home_sec._refresh_folder_list()

        # -------------------------------------------------------------
        # Documents refresh
        # -------------------------------------------------------------

        elif key == "documents":

            self._doc_sec._refresh_folders()

            # Refresh outputs too so newly saved
            # Canvas/Sketch files appear immediately.
            self._doc_sec._refresh_outputs()

    # =========================================================================
    # CLOSE EVENT
    # =========================================================================

    def closeEvent(
        self,
        event,
    ):

        # ──────────────────────────────────────────────────────────────
        # Stop Summarizer
        # ──────────────────────────────────────────────────────────────

        try:
            self._summ_sec.shutdown()
        except Exception:
            pass

        # ──────────────────────────────────────────────────────────────
        # Stop Sketch camera
        # ──────────────────────────────────────────────────────────────

        try:
            self._sketch_sec.shutdown()
        except Exception:
            pass

        event.accept()