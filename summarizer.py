# summarizer.py

from __future__ import annotations

import os
import socket
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from config import (
    DOCUMENTS_DIR,
    SUMMARIZE_SCRIPT,
    STREAMLIT_PORT,
    STREAMLIT_URL,
)


class SummarizerSection(QWidget):

    POLL_MS = 500
    MAX_MS = 45_000

    def __init__(self, parent=None):
        super().__init__(parent)

        self._proc = None
        self._booted = False
        self._waited = 0

        self._build_ui()

    # =========================================================================
    # UI
    # =========================================================================

    def _build_ui(self):

        lay = QVBoxLayout(self)

        lay.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self._status = QLabel(
            "Click  ✦ Summarizer  in the sidebar to start.\n\n"
            "PDFs uploaded from the Home tab will be accessible inside."
        )

        self._status.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self._status.setStyleSheet(
            "color:#aaaacc;"
            "font-size:15px;"
        )

        lay.addWidget(
            self._status
        )

        self._web = QWebEngineView()

        self._web.hide()

        lay.addWidget(
            self._web
        )

    # =========================================================================
    # BOOT STREAMLIT
    # =========================================================================

    def boot(self):
        """
        Called once when the user first navigates to Summarizer.
        """

        if self._booted:
            return

        self._booted = True

        # ---------------------------------------------------------------------
        # Check script
        # ---------------------------------------------------------------------

        if not SUMMARIZE_SCRIPT.exists():

            self._status.setText(
                "❌  summarize.py not found at:\n"
                f"{SUMMARIZE_SCRIPT}"
            )

            self._status.setStyleSheet(
                "color:#ff6666;"
                "font-size:13px;"
            )

            return

        # ---------------------------------------------------------------------
        # Environment
        # ---------------------------------------------------------------------

        env = {
            **os.environ,

            "_SUMMARIZE_WORKER": "1",

            "PDF_STUDIO_DOCS_DIR":
                str(DOCUMENTS_DIR),
        }

        # ---------------------------------------------------------------------
        # Windows process flags
        # ---------------------------------------------------------------------

        flags = (
            subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32"
            else 0
        )

        # ---------------------------------------------------------------------
        # Launch Streamlit
        # ---------------------------------------------------------------------

        try:

            self._proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(SUMMARIZE_SCRIPT),

                    "--server.port",
                    str(STREAMLIT_PORT),

                    "--server.headless",
                    "true",

                    "--browser.gatherUsageStats",
                    "false",
                ],

                env=env,

                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,

                creationflags=flags,
            )

        except Exception as e:

            self._status.setText(
                "❌  Could not start Summarizer.\n\n"
                f"{e}"
            )

            self._status.setStyleSheet(
                "color:#ff6666;"
                "font-size:13px;"
            )

            return

        # ---------------------------------------------------------------------
        # Wait for Streamlit
        # ---------------------------------------------------------------------

        self._status.setText(
            "⏳  Starting Summarizer…"
        )

        self._waited = 0

        QTimer.singleShot(
            self.POLL_MS,
            self._poll,
        )

    # =========================================================================
    # POLL FOR STREAMLIT
    # =========================================================================

    def _poll(self):

        ready = False

        # ---------------------------------------------------------------------
        # Test TCP connection
        # ---------------------------------------------------------------------

        try:

            with socket.create_connection(
                (
                    "localhost",
                    STREAMLIT_PORT,
                ),
                timeout=0.4,
            ):

                ready = True

        except OSError:
            pass

        # ---------------------------------------------------------------------
        # Ready
        # ---------------------------------------------------------------------

        if ready:

            self._status.hide()

            self._web.show()

            self._web.load(
                QUrl(
                    STREAMLIT_URL
                )
            )

            return

        # ---------------------------------------------------------------------
        # Still starting
        # ---------------------------------------------------------------------

        self._waited += self.POLL_MS

        if self._waited >= self.MAX_MS:

            self._status.setText(
                "❌  Streamlit did not start.\n\n"
                "Install it with:\n"
                "  pip install streamlit"
            )

            self._status.setStyleSheet(
                "color:#ff6666;"
                "font-size:13px;"
            )

            return

        dots = "." * (
            (
                self._waited
                // self.POLL_MS
            )
            % 4
        )

        self._status.setText(
            "⏳  Starting Summarizer"
            f"{dots}  "
            f"({self._waited // 1000}s)"
        )

        QTimer.singleShot(
            self.POLL_MS,
            self._poll,
        )

    # =========================================================================
    # SHUTDOWN
    # =========================================================================

    def shutdown(self):

        if (
            self._proc
            and
            self._proc.poll() is None
        ):

            self._proc.terminate()

            try:

                self._proc.wait(
                    timeout=3
                )

            except Exception:

                self._proc.kill()