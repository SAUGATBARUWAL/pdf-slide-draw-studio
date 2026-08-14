from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QDialog,
    QScrollArea,
)

from config import DOCUMENTS_DIR

from utils import (
    list_folders,
    safe_delete_folder,
    qmsg_info,
    qmsg_warn,
    qmsg_err,
    qmsg_ask,
)

from workers import ConvertWorker


class FolderNameDialog(QDialog):
    def __init__(self, parent, default: str = ""):
        super().__init__(parent)

        self.setWindowTitle("Name this folder")
        self.setFixedSize(380, 150)

        self.result_name: str | None = None

        lay = QVBoxLayout(self)

        lay.setContentsMargins(
            24, 20, 24, 16
        )

        lay.setSpacing(12)

        lay.addWidget(
            QLabel(
                "Enter a name for the output folder:"
            )
        )

        self.entry = QLineEdit(default)

        self.entry.returnPressed.connect(
            self._ok
        )

        lay.addWidget(
            self.entry
        )

        row = QHBoxLayout()

        row.setSpacing(10)

        ok = QPushButton("OK")
        ok.setObjectName("action_btn")

        can = QPushButton("Cancel")
        can.setObjectName("action_btn")
        can.setStyleSheet(
            "background-color:#444;"
        )

        ok.clicked.connect(
            self._ok
        )

        can.clicked.connect(
            self.reject
        )

        row.addStretch()
        row.addWidget(ok)
        row.addWidget(can)

        lay.addLayout(row)

    def _ok(self):

        name = "".join(
            c
            for c in self.entry.text().strip()
            if c.isalnum()
            or c in (" ", "_", "-")
        ).strip()

        if name:

            self.result_name = name
            self.accept()

        else:

            qmsg_warn(
                self,
                "Invalid name",
                "Please enter a valid folder name."
            )


class HomeSection(QWidget):

    folder_changed = pyqtSignal()

    def __init__(self, parent=None):

        super().__init__(parent)

        self._workers: list[ConvertWorker] = []

        self._build_ui()

    def _build_ui(self):

        lay = QVBoxLayout(self)

        lay.setContentsMargins(
            40, 40, 40, 20
        )

        lay.setSpacing(16)

        # Banner
        banner = QFrame()
        banner.setObjectName("card")

        b = QVBoxLayout(banner)

        b.setContentsMargins(
            30, 26, 30, 26
        )

        b.setSpacing(8)

        t = QLabel(
            "✏️  PDF Slide & Draw Studio"
        )

        t.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        t.setStyleSheet(
            "font-size:30px;"
            "font-weight:bold;"
            "color:#e0e0ff;"
        )

        b.addWidget(t)

        sub = QLabel(
            "Upload PDF files here."
        )

        sub.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        sub.setStyleSheet(
            "color:#9090bb;"
            "font-size:13px;"
        )

        sub.setWordWrap(True)

        b.addWidget(sub)

        lay.addWidget(
            banner
        )

        # Upload button
        btn = QPushButton(
            "📂  Upload PDF"
        )

        btn.setObjectName(
            "action_btn"
        )

        btn.setFixedHeight(
            46
        )

        btn.setStyleSheet(
            "font-size:15px;"
        )

        btn.clicked.connect(
            self._upload_pdf
        )

        lay.addWidget(
            btn
        )

        # Folder list
        lbl = QLabel(
            "Uploaded Documents  "
            "(shared with Documents & Summarizer)"
        )

        lbl.setStyleSheet(
            "color:#aaaacc;"
            "font-weight:bold;"
        )

        lay.addWidget(
            lbl
        )

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setMinimumHeight(
            200
        )

        self._fc = QWidget()

        self._fl = QVBoxLayout(
            self._fc
        )

        self._fl.setSpacing(
            6
        )

        self._fl.setContentsMargins(
            4, 4, 4, 4
        )

        self._fl.addStretch()

        self.scroll.setWidget(
            self._fc
        )

        lay.addWidget(
            self.scroll
        )

        self._refresh_folder_list()

    def _upload_pdf(self):

        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select PDF(s)",
            "",
            "PDF files (*.pdf)"
        )

        for path_str in paths:

            pdf = Path(
                path_str
            )

            dlg = FolderNameDialog(
                self,
                pdf.stem
            )

            if (
                dlg.exec()
                != QDialog.DialogCode.Accepted
                or not dlg.result_name
            ):
                continue

            dest = (
                DOCUMENTS_DIR
                / dlg.result_name
            )

            if dest.exists():

                if not qmsg_ask(
                    self,
                    "Overwrite?",
                    f"'{dlg.result_name}' exists. "
                    "Overwrite?"
                ):
                    continue

                ok, err = safe_delete_folder(
                    dest
                )

                if not ok:

                    qmsg_err(
                        self,
                        "Cannot overwrite",
                        err
                    )

                    continue

            worker = ConvertWorker(
                pdf,
                dest
            )

            worker.done.connect(
                self._on_done
            )

            worker.error.connect(
                lambda e:
                qmsg_err(
                    self,
                    "Conversion error",
                    e
                )
            )

            worker.start()

            self._workers.append(
                worker
            )

    def _on_done(
        self,
        n: int,
        name: str
    ):

        qmsg_info(
            self,
            "Upload complete",
            f"✅  {n} page(s) saved to '{name}'\n\n"
            "Now available in Documents and Summarizer."
        )

        self._refresh_folder_list()

        self.folder_changed.emit()

    def _delete_folder(
        self,
        folder: Path
    ):

        if not qmsg_ask(
            self,
            "Delete folder",
            f"Permanently delete '{folder.name}' "
            "and all its images?"
        ):
            return

        ok, err = safe_delete_folder(
            folder
        )

        if not ok:

            qmsg_err(
                self,
                "Delete failed",
                err
            )

            return

        self._refresh_folder_list()

        self.folder_changed.emit()

    def _refresh_folder_list(self):

        while self._fl.count() > 1:

            item = self._fl.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        folders = list_folders()

        if not folders:

            lbl = QLabel(
                "No folders yet — upload a PDF above."
            )

            lbl.setStyleSheet(
                "color:#666688;"
                "padding:12px;"
            )

            self._fl.insertWidget(
                0,
                lbl
            )

            return

        for folder in folders:

            count = len(
                list(
                    folder.glob("*.png")
                )
            )

            row = QWidget()

            rl = QHBoxLayout(
                row
            )

            rl.setContentsMargins(
                4, 2, 4, 2
            )

            rl.setSpacing(
                8
            )

            rl.addWidget(
                QLabel(
                    f"📁  {folder.name}   "
                    f"({count} page"
                    f"{'s' if count != 1 else ''})"
                ),
                stretch=1
            )

            delete_btn = QPushButton(
                "🗑 Delete"
            )

            delete_btn.setObjectName(
                "danger_btn"
            )

            delete_btn.setFixedWidth(
                90
            )

            delete_btn.clicked.connect(
                lambda _, f=folder:
                self._delete_folder(f)
            )

            rl.addWidget(
                delete_btn
            )

            self._fl.insertWidget(
                self._fl.count() - 1,
                row
            )