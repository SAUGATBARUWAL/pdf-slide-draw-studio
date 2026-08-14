import shutil
from pathlib import Path

import fitz
from PyQt6.QtWidgets import QMessageBox

from config import DOCUMENTS_DIR


# ─────────────────────────────────────────────
# Folder utilities
# ─────────────────────────────────────────────

def list_folders() -> list[Path]:
    if not DOCUMENTS_DIR.exists():
        return []

    return sorted(
        p for p in DOCUMENTS_DIR.iterdir()
        if p.is_dir()
    )


def safe_delete_folder(
    folder: Path
) -> tuple[bool, str]:

    try:
        shutil.rmtree(folder)
        return True, ""

    except PermissionError as e:
        return (
            False,
            f"Permission denied — close any open files "
            f"in '{folder.name}'.\n\n{e}"
        )

    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────
# PDF → PNG
# ─────────────────────────────────────────────

def pdf_to_pngs(
    pdf_path: Path,
    output_folder: Path,
    dpi: int = 150
) -> list[Path]:

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    doc = fitz.open(
        str(pdf_path)
    )

    saved = []

    try:
        for i, page in enumerate(doc):

            pix = page.get_pixmap(
                matrix=fitz.Matrix(
                    dpi / 72,
                    dpi / 72
                )
            )

            output_path = (
                output_folder
                / f"page_{i + 1:03d}.png"
            )

            pix.save(
                str(output_path)
            )

            saved.append(output_path)

    finally:
        doc.close()

    return saved


# ─────────────────────────────────────────────
# QMessageBox helpers
# ─────────────────────────────────────────────

def qmsg_info(parent, title, text):
    QMessageBox.information(
        parent,
        title,
        text
    )


def qmsg_warn(parent, title, text):
    QMessageBox.warning(
        parent,
        title,
        text
    )


def qmsg_err(parent, title, text):
    QMessageBox.critical(
        parent,
        title,
        text
    )


def qmsg_ask(
    parent,
    title,
    text
) -> bool:

    result = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes
        | QMessageBox.StandardButton.No
    )

    return (
        result
        == QMessageBox.StandardButton.Yes
    )