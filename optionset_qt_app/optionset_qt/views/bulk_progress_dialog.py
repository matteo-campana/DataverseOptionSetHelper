"""Bulk-operation progress dialog with log output and cancel."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class BulkProgressDialog(QDialog):
    """
    Non-modal dialog that shows batch progress, detailed log messages,
    and a Close/Cancel button.
    """

    cancel_requested = Signal()

    def __init__(self, title: str = "Bulk Operation", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(560, 380)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)

        # ── header ──────────────────────────────────────────
        self.lbl_header = QLabel(title)
        self.lbl_header.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.lbl_header)

        # ── progress bar ────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.lbl_batch = QLabel("Waiting …")
        layout.addWidget(self.lbl_batch)

        # ── log area ────────────────────────────────────────
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet(
            "QTextEdit { font-family: 'Cascadia Mono', 'Consolas', monospace; font-size: 12px; }"
        )
        layout.addWidget(self.txt_log, stretch=1)

        # ── buttons ─────────────────────────────────────────
        self.btn_close = QPushButton("Cancel")
        self.btn_close.clicked.connect(self._on_close)
        layout.addWidget(self.btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        self._finished = False

    # ── public API ──────────────────────────────────────────
    def set_total_batches(self, n: int) -> None:
        self.progress_bar.setMaximum(n)
        self.progress_bar.setValue(0)

    def set_batch_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.lbl_batch.setText(f"Batch {current} / {total}")

    def append_log(self, text: str) -> None:
        self.txt_log.append(text)

    def mark_finished(self, summary: str = "") -> None:
        self._finished = True
        self.btn_close.setText("Close")
        if summary:
            self.txt_log.append(f"\n{summary}")
        self.lbl_batch.setText("Done")

    # ── internal ────────────────────────────────────────────
    def _on_close(self) -> None:
        if self._finished:
            self.accept()
        else:
            self.cancel_requested.emit()
            self.reject()
