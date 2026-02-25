"""
Application bootstrap – creates QApplication, loads the stylesheet,
and shows the main window.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from optionset_qt.main_window import MainWindow


_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _load_stylesheet() -> str:
    qss = _ASSETS_DIR / "styles.qss"
    if qss.is_file():
        return qss.read_text(encoding="utf-8")
    return ""


def run() -> int:
    """Entry-point called by main.py."""
    # Ensure the OptionSetHelper package can be found
    parent = str(Path(__file__).resolve().parents[2])
    if parent not in sys.path:
        sys.path.insert(0, parent)

    app = QApplication(sys.argv)
    app.setApplicationName("Dataverse OptionSet Helper")
    app.setOrganizationName("OptionSetHelper")

    ss = _load_stylesheet()
    if ss:
        app.setStyleSheet(ss)

    window = MainWindow()
    window.show()
    return app.exec()
