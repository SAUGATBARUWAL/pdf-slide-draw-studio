# documents.py

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QKeyEvent

from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QScrollArea,
    QTabWidget,
    QDialog,
)

from config import (
    DOCUMENTS_DIR,
    SAVED_OUTPUTS_DIR,
)

from utils import (
    list_folders,
    safe_delete_folder,
    qmsg_info,
    qmsg_warn,
    qmsg_err,
    qmsg_ask,
)

from workers import (
    ConvertWorker,
)


# ──────────────────────────────────────────────────────────────────────────────
# INLINE PRESENTATION WINDOW
# ──────────────────────────────────────────────────────────────────────────────

class PresentationDialog(QDialog):
    """
    Built-in presentation viewer.

    Loads PNG slides directly from the selected PDF folder.
    No presentation.py is required.
    """

    def __init__(
        self,
        slide_folder: Path,
        parent=None,
    ):
        super().__init__(parent)

        self.slide_folder = Path(slide_folder)

        self.slides = sorted(
            self.slide_folder.glob("*.png")
        )

        self.current_index = 0

        self.setWindowTitle(
            f"Presentation — {self.slide_folder.name}"
        )

        self.resize(
            1200,
            750,
        )

        self.setMinimumSize(
            800,
            500,
        )

        self.setStyleSheet(
            """
            QDialog {
                background: #080b12;
            }

            QLabel {
                color: #e2e8f0;
            }

            QPushButton {
                background: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }

            QPushButton:hover {
                background: #334155;
            }

            QPushButton:pressed {
                background: #0f172a;
            }

            QPushButton:disabled {
                color: #475569;
                background: #111827;
                border-color: #1e293b;
            }
            """
        )

        self._build_ui()
        self._load_slide()

    # =========================================================================
    # PRESENTATION UI
    # =========================================================================

    def _build_ui(self):

        root = QVBoxLayout(self)

        root.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        root.setSpacing(
            8
        )

        # ──────────────────────────────────────────────────────────────
        # Header
        # ──────────────────────────────────────────────────────────────

        header = QHBoxLayout()

        self.title_lbl = QLabel(
            self.slide_folder.name
        )

        self.title_lbl.setStyleSheet(
            "font-size:15px;"
            "font-weight:bold;"
            "color:#e2e8f0;"
        )

        header.addWidget(
            self.title_lbl,
            stretch=1,
        )

        self.counter_lbl = QLabel(
            ""
        )

        self.counter_lbl.setStyleSheet(
            "color:#94a3b8;"
            "font-size:11px;"
        )

        header.addWidget(
            self.counter_lbl
        )

        root.addLayout(
            header
        )

        # ──────────────────────────────────────────────────────────────
        # Slide area
        # ──────────────────────────────────────────────────────────────

        slide_frame = QFrame()

        slide_frame.setStyleSheet(
            """
            QFrame {
                background: #000000;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            """
        )

        slide_layout = QVBoxLayout(
            slide_frame
        )

        slide_layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        self.slide_label = QLabel()

        self.slide_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.slide_label.setStyleSheet(
            "background:#000000;"
        )

        self.slide_label.setMinimumSize(
            400,
            300,
        )

        slide_layout.addWidget(
            self.slide_label,
            stretch=1,
        )

        root.addWidget(
            slide_frame,
            stretch=1,
        )

        # ──────────────────────────────────────────────────────────────
        # Controls
        # ──────────────────────────────────────────────────────────────

        controls = QHBoxLayout()

        self.previous_btn = QPushButton(
            "◀ Previous"
        )

        self.previous_btn.clicked.connect(
            self._previous
        )

        controls.addWidget(
            self.previous_btn
        )

        self.next_btn = QPushButton(
            "Next ▶"
        )

        self.next_btn.clicked.connect(
            self._next
        )

        controls.addWidget(
            self.next_btn
        )

        controls.addStretch()

        self.fullscreen_btn = QPushButton(
            "⛶ Fullscreen"
        )

        self.fullscreen_btn.clicked.connect(
            self._toggle_fullscreen
        )

        controls.addWidget(
            self.fullscreen_btn
        )

        close_btn = QPushButton(
            "✕ Close"
        )

        close_btn.clicked.connect(
            self.close
        )

        controls.addWidget(
            close_btn
        )

        root.addLayout(
            controls
        )

        # ──────────────────────────────────────────────────────────────
        # Keyboard help
        # ──────────────────────────────────────────────────────────────

        help_lbl = QLabel(
            "← / → Navigate    "
            "Home / End First / Last    "
            "F Fullscreen    Esc Close"
        )

        help_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        help_lbl.setStyleSheet(
            "color:#475569;"
            "font-size:10px;"
        )

        root.addWidget(
            help_lbl
        )

    # =========================================================================
    # LOAD SLIDE
    # =========================================================================

    def _load_slide(self):

        if not self.slides:

            self.slide_label.clear()

            self.slide_label.setText(
                "No PNG slides found."
            )

            self.counter_lbl.setText(
                "0 / 0"
            )

            self.previous_btn.setEnabled(
                False
            )

            self.next_btn.setEnabled(
                False
            )

            return

        self.current_index = max(
            0,
            min(
                self.current_index,
                len(self.slides) - 1,
            ),
        )

        slide_path = self.slides[
            self.current_index
        ]

        pixmap = QPixmap(
            str(slide_path)
        )

        if pixmap.isNull():

            self.slide_label.clear()

            self.slide_label.setText(
                f"Could not load:\n"
                f"{slide_path.name}"
            )

        else:

            target_size = (
                self.slide_label.size()
            )

            if (
                target_size.width() < 100
                or
                target_size.height() < 100
            ):
                target_size = self.size()

            scaled = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            self.slide_label.setPixmap(
                scaled
            )

        self.title_lbl.setText(
            f"{self.slide_folder.name}  —  "
            f"{slide_path.name}"
        )

        self.counter_lbl.setText(
            f"{self.current_index + 1} / "
            f"{len(self.slides)}"
        )

        self.previous_btn.setEnabled(
            self.current_index > 0
        )

        self.next_btn.setEnabled(
            self.current_index
            <
            len(self.slides) - 1
        )

    # =========================================================================
    # PREVIOUS
    # =========================================================================

    def _previous(self):

        if self.current_index > 0:

            self.current_index -= 1

            self._load_slide()

    # =========================================================================
    # NEXT
    # =========================================================================

    def _next(self):

        if (
            self.current_index
            <
            len(self.slides) - 1
        ):

            self.current_index += 1

            self._load_slide()

    # =========================================================================
    # FULLSCREEN
    # =========================================================================

    def _toggle_fullscreen(self):

        if self.isFullScreen():

            self.showNormal()

            self.fullscreen_btn.setText(
                "⛶ Fullscreen"
            )

        else:

            self.showFullScreen()

            self.fullscreen_btn.setText(
                "🗗 Exit Fullscreen"
            )

        self._load_slide()

    # =========================================================================
    # RESIZE
    # =========================================================================

    def resizeEvent(
        self,
        event,
    ):

        super().resizeEvent(
            event
        )

        self._load_slide()

    # =========================================================================
    # KEYBOARD
    # =========================================================================

    def keyPressEvent(
        self,
        event: QKeyEvent,
    ):

        key = event.key()

        if key == Qt.Key.Key_Left:

            self._previous()

        elif key == Qt.Key.Key_Right:

            self._next()

        elif key == Qt.Key.Key_Home:

            self.current_index = 0

            self._load_slide()

        elif key == Qt.Key.Key_End:

            self.current_index = (
                len(self.slides) - 1
            )

            self._load_slide()

        elif key == Qt.Key.Key_F:

            self._toggle_fullscreen()

        elif key == Qt.Key.Key_Escape:

            if self.isFullScreen():

                self.showNormal()

                self.fullscreen_btn.setText(
                    "⛶ Fullscreen"
                )

                self._load_slide()

            else:

                self.close()

        else:

            super().keyPressEvent(
                event
            )


# ──────────────────────────────────────────────────────────────────────────────
# DOCUMENT SECTION
# ──────────────────────────────────────────────────────────────────────────────

class DocumentSection(QWidget):

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self._pdf_path: Path | None = None

        self._selected_folder: Path | None = None

        self._conv_worker: ConvertWorker | None = None

        self._presentation_dialog: (
            PresentationDialog | None
        ) = None

        self._build_ui()

        self._tabs.currentChanged.connect(
            self._on_tab_changed
        )

        self._refresh_folders()

        self._refresh_outputs()

    # =========================================================================
    # UI
    # =========================================================================

    def _build_ui(self):

        lay = QVBoxLayout(self)

        lay.setContentsMargins(
            24,
            24,
            24,
            12,
        )

        lay.setSpacing(
            10
        )

        # ──────────────────────────────────────────────────────────────
        # Toolbar
        # ──────────────────────────────────────────────────────────────

        tb = QFrame()
        tb.setObjectName(
            "toolbar_card"
        )

        tbl = QHBoxLayout(tb)

        tbl.setContentsMargins(
            16,
            10,
            12,
            10,
        )

        t = QLabel(
            "📄  Document Presenter"
        )

        t.setStyleSheet(
            "font-size:18px;"
            "font-weight:bold;"
            "color:#e0e0ff;"
        )

        tbl.addWidget(
            t,
            stretch=1,
        )

        sel = QPushButton(
            "📂 Select PDF"
        )

        sel.setObjectName(
            "action_btn"
        )

        sel.setFixedHeight(
            36
        )

        sel.clicked.connect(
            self._select_pdf
        )

        tbl.addWidget(
            sel
        )

        conv = QPushButton(
            "⚙️ Convert"
        )

        conv.setObjectName(
            "green_btn"
        )

        conv.setFixedHeight(
            36
        )

        conv.clicked.connect(
            self._convert
        )

        tbl.addWidget(
            conv
        )

        lay.addWidget(
            tb
        )

        # ──────────────────────────────────────────────────────────────
        # PDF info
        # ──────────────────────────────────────────────────────────────

        info = QWidget()

        il = QGridLayout(
            info
        )

        il.setContentsMargins(
            4,
            0,
            4,
            0,
        )

        il.setSpacing(
            8
        )

        il.addWidget(
            self._bold("PDF:"),
            0,
            0,
        )

        self._pdf_lbl = QLabel(
            "None selected"
        )

        self._pdf_lbl.setStyleSheet(
            "color:#888899;"
        )

        il.addWidget(
            self._pdf_lbl,
            0,
            1,
        )

        il.addWidget(
            self._bold("Folder name:"),
            1,
            0,
        )

        self._folder_entry = QLineEdit()

        self._folder_entry.setPlaceholderText(
            "e.g.  Lecture_Week3"
        )

        il.addWidget(
            self._folder_entry,
            1,
            1,
        )

        il.setColumnStretch(
            1,
            1,
        )

        lay.addWidget(
            info
        )

        # ──────────────────────────────────────────────────────────────
        # Tabs
        # ──────────────────────────────────────────────────────────────

        self._tabs = QTabWidget()

        self._tabs.setStyleSheet(
            """
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
            """
        )

        self._tabs.addTab(
            self._build_folders_tab(),
            "📁  PDF Folders",
        )

        self._tabs.addTab(
            self._build_outputs_tab(),
            "💾  Saved Outputs",
        )

        lay.addWidget(
            self._tabs,
            stretch=1,
        )

        # ──────────────────────────────────────────────────────────────
        # Presentation bar
        # ──────────────────────────────────────────────────────────────

        pb = QFrame()

        pb.setObjectName(
            "present_bar"
        )

        pbl = QHBoxLayout(pb)

        pbl.setContentsMargins(
            16,
            8,
            16,
            8,
        )

        pbl.addWidget(
            self._bold("Selected:")
        )

        self._sel_lbl = QLabel(
            "None"
        )

        self._sel_lbl.setStyleSheet(
            "color:#888899;"
        )

        pbl.addWidget(
            self._sel_lbl,
            stretch=1,
        )

        self._present_btn = QPushButton(
            "▶  Present"
        )

        self._present_btn.setObjectName(
            "blue_btn"
        )

        self._present_btn.setFixedHeight(
            36
        )

        self._present_btn.clicked.connect(
            self._launch_presentation
        )

        pbl.addWidget(
            self._present_btn
        )

        lay.addWidget(
            pb
        )

        # ──────────────────────────────────────────────────────────────
        # Status
        # ──────────────────────────────────────────────────────────────

        self._status = QLabel(
            ""
        )

        self._status.setStyleSheet(
            "color:#55cc55;"
            "font-size:12px;"
        )

        self._status.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        lay.addWidget(
            self._status
        )

    # =========================================================================
    # PDF FOLDERS TAB
    # =========================================================================

    def _build_folders_tab(
        self,
    ) -> QWidget:

        w = QWidget()

        lay = QVBoxLayout(w)

        lay.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        lay.setSpacing(
            6
        )

        tip = QLabel(
            "💡  PDFs uploaded via Home appear below automatically."
        )

        tip.setStyleSheet(
            "color:#555577;"
            "font-size:11px;"
            "padding:0 4px;"
        )

        lay.addWidget(
            tip
        )

        self._scroll = QScrollArea()

        self._scroll.setWidgetResizable(
            True
        )

        self._fc = QWidget()

        self._fl = QVBoxLayout(
            self._fc
        )

        self._fl.setSpacing(
            4
        )

        self._fl.setContentsMargins(
            4,
            4,
            4,
            4,
        )

        self._fl.addStretch()

        self._scroll.setWidget(
            self._fc
        )

        lay.addWidget(
            self._scroll,
            stretch=1,
        )

        return w

    # =========================================================================
    # SAVED OUTPUTS TAB
    # =========================================================================

    def _build_outputs_tab(
        self,
    ) -> QWidget:

        w = QWidget()

        lay = QVBoxLayout(w)

        lay.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        lay.setSpacing(
            6
        )

        hdr = QHBoxLayout()

        tip = QLabel(
            "💾  Files saved from Canvas, Sketch, "
            "Summarizer and Presentation."
        )

        tip.setStyleSheet(
            "color:#555577;"
            "font-size:11px;"
        )

        hdr.addWidget(
            tip,
            stretch=1,
        )

        ref_btn = QPushButton(
            "🔄 Refresh"
        )

        ref_btn.setObjectName(
            "action_btn"
        )

        ref_btn.setFixedHeight(
            28
        )

        ref_btn.clicked.connect(
            self._refresh_outputs
        )

        hdr.addWidget(
            ref_btn
        )

        open_btn = QPushButton(
            "📂 Open Folder"
        )

        open_btn.setObjectName(
            "action_btn"
        )

        open_btn.setFixedHeight(
            28
        )

        open_btn.clicked.connect(
            self._open_outputs_folder
        )

        hdr.addWidget(
            open_btn
        )

        lay.addLayout(
            hdr
        )

        self._out_scroll = QScrollArea()

        self._out_scroll.setWidgetResizable(
            True
        )

        self._out_container = QWidget()

        self._out_layout = QVBoxLayout(
            self._out_container
        )

        self._out_layout.setSpacing(
            4
        )

        self._out_layout.setContentsMargins(
            4,
            4,
            4,
            4,
        )

        self._out_layout.addStretch()

        self._out_scroll.setWidget(
            self._out_container
        )

        lay.addWidget(
            self._out_scroll,
            stretch=1,
        )

        return w

    # =========================================================================
    # HELPER
    # =========================================================================

    @staticmethod
    def _bold(
        text: str,
    ) -> QLabel:

        label = QLabel(
            text
        )

        label.setStyleSheet(
            "font-weight:bold;"
        )

        return label

    # =========================================================================
    # SELECT PDF
    # =========================================================================

    def _select_pdf(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a PDF",
            "",
            "PDF files (*.pdf)",
        )

        if path:

            self._pdf_path = Path(
                path
            )

            self._pdf_lbl.setText(
                self._pdf_path.name
            )

            self._pdf_lbl.setStyleSheet(
                "color:#e0e0ff;"
            )

            self._folder_entry.setText(
                self._pdf_path.stem
            )

    # =========================================================================
    # CONVERT
    # =========================================================================

    def _convert(self):

        if not self._pdf_path:

            qmsg_warn(
                self,
                "No PDF",
                "Please select a PDF first.",
            )

            return

        name = "".join(
            c
            for c in self._folder_entry.text().strip()
            if c.isalnum()
            or c in (
                " ",
                "_",
                "-",
            )
        ).strip()

        if not name:

            qmsg_warn(
                self,
                "No name",
                "Please enter a folder name.",
            )

            return

        dest = (
            DOCUMENTS_DIR
            / name
        )

        if dest.exists():

            if not qmsg_ask(
                self,
                "Overwrite?",
                f"'{name}' exists. Overwrite?",
            ):
                return

            ok, err = safe_delete_folder(
                dest
            )

            if not ok:

                qmsg_err(
                    self,
                    "Cannot overwrite",
                    err,
                )

                return

        self._status.setStyleSheet(
            "color:#ffcc44;"
            "font-size:12px;"
        )

        self._status.setText(
            "⏳  Converting…"
        )

        self._conv_worker = ConvertWorker(
            self._pdf_path,
            dest,
        )

        self._conv_worker.done.connect(
            self._on_convert_done
        )

        self._conv_worker.error.connect(
            self._on_convert_err
        )

        self._conv_worker.start()

    # =========================================================================
    # CONVERSION COMPLETE
    # =========================================================================

    def _on_convert_done(
        self,
        n: int,
        name: str,
    ):

        self._status.setStyleSheet(
            "color:#55cc55;"
            "font-size:12px;"
        )

        self._status.setText(
            f"✅  {n} page(s) saved to '{name}'"
        )

        self._refresh_folders()

    def _on_convert_err(
        self,
        err: str,
    ):

        qmsg_err(
            self,
            "Conversion error",
            err,
        )

        self._status.setStyleSheet(
            "color:#cc4444;"
            "font-size:12px;"
        )

        self._status.setText(
            "❌  Conversion failed."
        )

    # =========================================================================
    # FOLDER SELECTION
    # =========================================================================

    def _select_folder(
        self,
        folder: Path,
    ):

        self._selected_folder = folder

        self._sel_lbl.setText(
            f"📁  {folder.name}"
        )

        self._sel_lbl.setStyleSheet(
            "color:#ccccff;"
        )

        self._refresh_folders()

    # =========================================================================
    # PRESENTATION
    # =========================================================================

    def _launch_presentation(self):

        if not self._selected_folder:

            qmsg_warn(
                self,
                "No folder",
                "Click a folder in the list first, "
                "then click Present.",
            )

            return

        if not self._selected_folder.exists():

            qmsg_warn(
                self,
                "Folder gone",
                f"'{self._selected_folder.name}' "
                "no longer exists.",
            )

            self._selected_folder = None

            self._sel_lbl.setText(
                "None"
            )

            self._sel_lbl.setStyleSheet(
                "color:#888899;"
            )

            self._refresh_folders()

            return

        slides = sorted(
            self._selected_folder.glob(
                "*.png"
            )
        )

        if not slides:

            qmsg_warn(
                self,
                "No slides",
                f"'{self._selected_folder.name}' "
                "has no PNG slides.\n"
                "Convert a PDF first.",
            )

            return

        # If a presentation is already open,
        # bring it forward.
        if (
            self._presentation_dialog
            and
            self._presentation_dialog.isVisible()
        ):

            self._presentation_dialog.raise_()

            self._presentation_dialog.activateWindow()

            return

        self._present_btn.setEnabled(
            False
        )

        self._status.setStyleSheet(
            "color:#ffcc44;"
            "font-size:12px;"
        )

        self._status.setText(
            "⏳  Opening presentation…"
        )

        self._presentation_dialog = (
            PresentationDialog(
                self._selected_folder,
                self,
            )
        )

        self._presentation_dialog.finished.connect(
            self._on_presentation_closed
        )

        self._presentation_dialog.show()

        self._presentation_dialog.raise_()

        self._presentation_dialog.activateWindow()

        self._status.setStyleSheet(
            "color:#55cc55;"
            "font-size:12px;"
        )

        self._status.setText(
            f"✅  Presenting "
            f"'{self._selected_folder.name}'"
        )

    # =========================================================================
    # PRESENTATION CLOSED
    # =========================================================================

    def _on_presentation_closed(
        self,
        result: int,
    ):

        self._present_btn.setEnabled(
            True
        )

        self._status.setStyleSheet(
            "color:#55cc55;"
            "font-size:12px;"
        )

        self._status.setText(
            "✅  Presentation closed."
        )

        self._presentation_dialog = None

    # =========================================================================
    # REFRESH FOLDERS
    # =========================================================================

    def _refresh_folders(self):

        while self._fl.count() > 1:

            item = self._fl.takeAt(
                0
            )

            if item.widget():

                item.widget().deleteLater()

        if (
            self._selected_folder
            and
            not self._selected_folder.exists()
        ):

            self._selected_folder = None

            self._sel_lbl.setText(
                "None"
            )

            self._sel_lbl.setStyleSheet(
                "color:#888899;"
            )

        folders = list_folders()

        if not folders:

            lbl = QLabel(
                "No folders yet.  Upload a PDF from the Home tab."
            )

            lbl.setStyleSheet(
                "color:#666688;"
                "padding:10px;"
            )

            self._fl.insertWidget(
                0,
                lbl
            )

            return

        for folder in folders:

            count = len(
                list(
                    folder.glob(
                        "*.png"
                    )
                )
            )

            selected = (
                self._selected_folder
                == folder
            )

            btn = QPushButton(
                f"📁  {folder.name}\n"
                f"{count} page"
                f"{'s' if count != 1 else ''}"
            )

            btn.setObjectName(
                "folder_item"
            )

            btn.setProperty(
                "selected",
                (
                    "true"
                    if selected
                    else
                    "false"
                )
            )

            btn.setFixedHeight(
                48
            )

            btn.clicked.connect(
                lambda _,
                f=folder:
                self._select_folder(f)
            )

            btn.style().unpolish(
                btn
            )

            btn.style().polish(
                btn
            )

            self._fl.insertWidget(
                self._fl.count() - 1,
                btn
            )

    # =========================================================================
    # REFRESH OUTPUTS
    # =========================================================================

    def _refresh_outputs(self):

        while self._out_layout.count() > 1:

            item = (
                self._out_layout.takeAt(
                    0
                )
            )

            if item.widget():

                item.widget().deleteLater()

        files = (
            sorted(
                [
                    f
                    for f
                    in SAVED_OUTPUTS_DIR.iterdir()
                    if f.is_file()
                ],
                key=lambda f:
                f.stat().st_mtime,
                reverse=True,
            )
            if SAVED_OUTPUTS_DIR.exists()
            else []
        )

        if not files:

            lbl = QLabel(
                "No saved files yet.\n"
                "Save from Canvas, Sketch, "
                "Summarizer or Presentation."
            )

            lbl.setStyleSheet(
                "color:#666688;"
                "padding:14px;"
            )

            lbl.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            self._out_layout.insertWidget(
                0,
                lbl
            )

            return

        FILE_ICONS = {
            ".png": "🖼",
            ".jpg": "🖼",
            ".jpeg": "🖼",
            ".pdf": "📄",
            ".txt": "📝",
            ".md": "📝",
        }

        for f in files:

            size_kb = (
                f.stat().st_size
                // 1024
            )

            icon = FILE_ICONS.get(
                f.suffix.lower(),
                "📎"
            )

            row = QWidget()

            row.setStyleSheet(
                "background:#1a1e2a;"
                "border-radius:8px;"
                "border:1px solid #1e2230;"
            )

            row_lay = QHBoxLayout(
                row
            )

            row_lay.setContentsMargins(
                10,
                6,
                10,
                6,
            )

            row_lay.setSpacing(
                10
            )

            # Icon
            icon_lbl = QLabel(
                icon
            )

            icon_lbl.setStyleSheet(
                "font-size:20px;"
            )

            icon_lbl.setFixedWidth(
                28
            )

            row_lay.addWidget(
                icon_lbl
            )

            # Information
            info_w = QWidget()

            info_lay = QVBoxLayout(
                info_w
            )

            info_lay.setContentsMargins(
                0,
                0,
                0,
                0,
            )

            info_lay.setSpacing(
                2
            )

            name_lbl = QLabel(
                f.name
            )

            name_lbl.setStyleSheet(
                "color:#e0e0ff;"
                "font-size:12px;"
                "font-weight:bold;"
            )

            suffix = (
                f.suffix.upper()[1:]
                if f.suffix
                else "FILE"
            )

            size_lbl = QLabel(
                f"{size_kb} KB  ·  {suffix}"
            )

            size_lbl.setStyleSheet(
                "color:#555577;"
                "font-size:10px;"
            )

            info_lay.addWidget(
                name_lbl
            )

            info_lay.addWidget(
                size_lbl
            )

            row_lay.addWidget(
                info_w,
                stretch=1
            )

            # Open
            open_btn = QPushButton(
                "📂  Open"
            )

            open_btn.setFixedHeight(
                30
            )

            open_btn.setFixedWidth(
                80
            )

            open_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #1e3a5f;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 6px;
                }

                QPushButton:hover {
                    background-color: #2a5a9a;
                }

                QPushButton:pressed {
                    background-color: #1a3070;
                }
                """
            )

            open_btn.clicked.connect(
                lambda _,
                p=f:
                self._open_file(p)
            )

            row_lay.addWidget(
                open_btn
            )

            # Delete
            del_btn = QPushButton(
                "🗑  Delete"
            )

            del_btn.setFixedHeight(
                30
            )

            del_btn.setFixedWidth(
                80
            )

            del_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #7f1d1d;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px 6px;
                }

                QPushButton:hover {
                    background-color: #b91c1c;
                }

                QPushButton:pressed {
                    background-color: #6b1414;
                }
                """
            )

            del_btn.setToolTip(
                "Delete this file permanently"
            )

            del_btn.clicked.connect(
                lambda _,
                p=f:
                self._delete_output(p)
            )

            row_lay.addWidget(
                del_btn
            )

            self._out_layout.insertWidget(
                self._out_layout.count() - 1,
                row
            )

    # =========================================================================
    # OPEN FILE
    # =========================================================================

    def _open_file(
        self,
        path: Path,
    ):

        try:

            if sys.platform == "win32":

                os.startfile(
                    path
                )

            elif sys.platform == "darwin":

                subprocess.Popen(
                    [
                        "open",
                        str(path),
                    ]
                )

            else:

                subprocess.Popen(
                    [
                        "xdg-open",
                        str(path),
                    ]
                )

        except Exception as e:

            qmsg_err(
                self,
                "Cannot open file",
                str(e),
            )

    # =========================================================================
    # DELETE OUTPUT
    # =========================================================================

    def _delete_output(
        self,
        path: Path,
    ):

        if not qmsg_ask(
            self,
            "Delete file",
            f"Permanently delete '{path.name}'?",
        ):

            return

        try:

            path.unlink()

            self._refresh_outputs()

        except Exception as e:

            qmsg_err(
                self,
                "Cannot delete",
                str(e),
            )

    # =========================================================================
    # OPEN OUTPUTS FOLDER
    # =========================================================================

    def _open_outputs_folder(self):

        SAVED_OUTPUTS_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:

            if sys.platform == "win32":

                os.startfile(
                    SAVED_OUTPUTS_DIR
                )

            elif sys.platform == "darwin":

                subprocess.Popen(
                    [
                        "open",
                        str(SAVED_OUTPUTS_DIR),
                    ]
                )

            else:

                subprocess.Popen(
                    [
                        "xdg-open",
                        str(SAVED_OUTPUTS_DIR),
                    ]
                )

        except Exception as e:

            qmsg_err(
                self,
                "Cannot open folder",
                str(e),
            )

    # =========================================================================
    # TAB CHANGE
    # =========================================================================

    def _on_tab_changed(
        self,
        idx: int,
    ):

        if idx == 1:

            self._refresh_outputs()