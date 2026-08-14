from __future__ import annotations

import sys
import subprocess
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from utils import pdf_to_pngs
class ConvertWorker(QThread):
    done  = pyqtSignal(int, str)   # (page_count, folder_name)
    error = pyqtSignal(str)

    def __init__(self, pdf_path: Path, output_folder: Path):
        super().__init__()
        self.pdf_path      = pdf_path
        self.output_folder = output_folder

    def run(self):
        try:
            pages = pdf_to_pngs(self.pdf_path, self.output_folder)
            self.done.emit(len(pages), self.output_folder.name)
        except Exception as e:
            self.error.emit(str(e))

class ScriptWorker(QThread):
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, script: Path, args: list[str] | None = None,
                 new_console: bool = True):
        super().__init__()
        self.script      = script
        self.args        = args or []
        self.new_console = new_console

    def run(self):                           # ← was missing; now correct
        try:
            cmd = [sys.executable, str(self.script)] + self.args
            if sys.platform == "win32":
                if self.new_console:
                    flags = subprocess.CREATE_NEW_CONSOLE
                else:
                    flags = subprocess.CREATE_NO_WINDOW
            else:
                flags = 0

            result = subprocess.run(
                cmd,
                creationflags=flags,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode not in (0, 1):   # 1 = user closed window (OK)
                stderr_snippet = (result.stderr or "").strip()[:2000]
                self.error.emit(
                    f"{self.script.name} exited with code {result.returncode}.\n\n"
                    + (stderr_snippet if stderr_snippet
                       else "Run the script directly in a terminal for the full traceback.")
                )
            else:
                self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))