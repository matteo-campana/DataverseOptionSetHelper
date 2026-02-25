"""
MainWindow – glues the UI layout to the background workers.

All Dataverse calls run in a QThread so the GUI never blocks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, QThread, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
)

from OptionSetHelper import DataverseOptionSetService, OptionItem

from optionset_qt.controllers.main_controller import (
    AuthWorker,
    BulkOperationWorker,
    CreateGlobalWorker,
    FetchOptionsWorker,
    InsertSingleWorker,
    ListGlobalWorker,
    load_options_from_file,
)
from optionset_qt.models.optionset_model import (
    OptionSetInfo,
    extract_option_values,
    extract_optionset_infos,
)
from optionset_qt.ui.main_window_ui import Ui_MainWindow
from optionset_qt.views.bulk_progress_dialog import BulkProgressDialog
from optionset_qt.views.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self) -> None:
        super().__init__()

        # ── UI setup ────────────────────────────────────────
        self.ui = Ui_MainWindow()
        self.ui.setup_ui(self)

        # ── state ───────────────────────────────────────────
        self._settings = QSettings("OptionSetHelper", "QtApp")
        self._svc: Optional[DataverseOptionSetService] = None
        self._optionset_infos: list[OptionSetInfo] = []
        self._thread: Optional[QThread] = None  # current bg thread
        self._env_path: str = self._settings.value("env_path", "")

        # ── wire signals ────────────────────────────────────
        self._connect_actions()

        # ── auto-connect if .env is known ───────────────────
        if self._env_path and Path(self._env_path).is_file():
            self._authenticate(self._env_path)
        else:
            self._log("Open Settings (File → Settings) to configure your .env file.")

    # ═══════════════════════════════════════════════════════════
    #  Signal wiring
    # ═══════════════════════════════════════════════════════════

    def _connect_actions(self) -> None:
        ui = self.ui

        # File menu
        ui.action_settings.triggered.connect(self._open_settings)
        ui.action_quit.triggered.connect(self.close)

        # Actions menu / toolbar
        ui.action_refresh.triggered.connect(self._refresh_list)
        ui.action_create_global.triggered.connect(self._create_global)
        ui.action_insert_single.triggered.connect(self._insert_single)
        ui.action_bulk_insert.triggered.connect(lambda: self._bulk_op("insert"))
        ui.action_bulk_update.triggered.connect(lambda: self._bulk_op("update"))
        ui.action_bulk_delete.triggered.connect(lambda: self._bulk_op("delete"))

        # Tables
        ui.tbl_optionsets.currentCellChanged.connect(self._on_optionset_selected)

        # Search
        ui.btn_search.clicked.connect(self._filter_table)
        ui.search_input.returnPressed.connect(self._filter_table)

    # ═══════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════

    def _log(self, msg: str) -> None:
        self.ui.log_output.append(msg)

    def _status(self, msg: str) -> None:
        self.ui.lbl_status.setText(msg)

    def _ensure_connected(self) -> bool:
        if self._svc is not None:
            return True
        QMessageBox.warning(
            self, "Not connected",
            "Please configure your .env first (File → Settings).",
        )
        return False

    def _start_worker(self, worker, thread: QThread) -> None:
        """Move *worker* to *thread*, start it, and keep a reference."""
        # clean previous thread
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()

    def _ask_optionset_name(self, title: str = "OptionSet name") -> str | None:
        row = self.ui.tbl_optionsets.currentRow()
        default = ""
        if row >= 0 and row < len(self._optionset_infos):
            default = self._optionset_infos[row].name
        name, ok = QInputDialog.getText(self, title, "OptionSet name:", text=default)
        if ok and name.strip():
            return name.strip()
        return None

    # ═══════════════════════════════════════════════════════════
    #  Settings / Authentication
    # ═══════════════════════════════════════════════════════════

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self, self._env_path)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            path = dlg.env_path()
            if path:
                self._env_path = path
                self._settings.setValue("env_path", path)
                self._authenticate(path)

    def _authenticate(self, env_path: str) -> None:
        self._status("Authenticating …")
        thread = QThread(self)
        worker = AuthWorker(env_path)
        worker.log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.finished.connect(self._on_auth_finished)
        worker.finished.connect(thread.quit)
        self._start_worker(worker, thread)
        # prevent GC
        self._auth_worker = worker

    def _on_auth_finished(self, svc: DataverseOptionSetService | None) -> None:
        self._svc = svc
        if svc:
            self._status("Connected")
            self._refresh_list()
        else:
            self._status("Authentication failed")

    # ═══════════════════════════════════════════════════════════
    #  List / Search
    # ═══════════════════════════════════════════════════════════

    def _refresh_list(self) -> None:
        if not self._ensure_connected():
            return
        self._status("Loading OptionSets …")
        thread = QThread(self)
        worker = ListGlobalWorker(self._svc)
        worker.log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.finished.connect(self._on_list_received)
        worker.finished.connect(thread.quit)
        self._start_worker(worker, thread)
        self._list_worker = worker

    def _on_list_received(self, raw_list: list) -> None:
        self._optionset_infos = extract_optionset_infos(raw_list)
        self._populate_optionsets_table(self._optionset_infos)
        self._status(f"{len(self._optionset_infos)} OptionSets loaded")

    def _populate_optionsets_table(self, infos: list[OptionSetInfo]) -> None:
        tbl = self.ui.tbl_optionsets
        tbl.setRowCount(0)
        for info in infos:
            r = tbl.rowCount()
            tbl.insertRow(r)
            tbl.setItem(r, 0, QTableWidgetItem(info.name))
            tbl.setItem(r, 1, QTableWidgetItem(info.display_label))
            tbl.setItem(r, 2, QTableWidgetItem(str(info.option_set_type)))
            item = QTableWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, info.option_count)
            tbl.setItem(r, 3, item)

    def _filter_table(self) -> None:
        text = self.ui.search_input.text().strip().lower()
        if not text:
            self._populate_optionsets_table(self._optionset_infos)
            return
        filtered = [
            i for i in self._optionset_infos
            if text in i.name.lower() or text in i.display_label.lower()
        ]
        self._populate_optionsets_table(filtered)

    # ═══════════════════════════════════════════════════════════
    #  Show options for selected OptionSet
    # ═══════════════════════════════════════════════════════════

    def _on_optionset_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if row < 0 or row >= len(self._optionset_infos):
            return
        info = self._optionset_infos[row]
        if info.name != self._optionset_infos[row].name:
            return
        # Use the raw data already fetched if available
        raw_opts = info.raw.get("Options", [])
        if raw_opts:
            self._show_options(info.name, raw_opts)
        else:
            self._fetch_options_remote(info.name)

    def _fetch_options_remote(self, name: str) -> None:
        if not self._svc:
            return
        self._status(f"Loading options for '{name}' …")
        thread = QThread(self)
        worker = FetchOptionsWorker(self._svc, name)
        worker.log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.finished.connect(lambda opts: self._show_options(name, opts))
        worker.finished.connect(thread.quit)
        self._start_worker(worker, thread)
        self._fetch_worker = worker

    def _show_options(self, name: str, raw_options: list) -> None:
        vals = extract_option_values(raw_options)
        self.ui.lbl_detail_title.setText(f"{name}  ({len(vals)} options)")
        tbl = self.ui.tbl_options
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        for v in vals:
            r = tbl.rowCount()
            tbl.insertRow(r)
            item_val = QTableWidgetItem()
            item_val.setData(Qt.ItemDataRole.DisplayRole, v.value)
            tbl.setItem(r, 0, item_val)
            tbl.setItem(r, 1, QTableWidgetItem(v.label))
        tbl.setSortingEnabled(True)
        self._status(f"Showing {len(vals)} options for '{name}'")

    # ═══════════════════════════════════════════════════════════
    #  Create global OptionSet
    # ═══════════════════════════════════════════════════════════

    def _create_global(self) -> None:
        if not self._ensure_connected():
            return
        name, ok = QInputDialog.getText(self, "Create Global OptionSet", "OptionSet name:")
        if not ok or not name.strip():
            return
        name = name.strip()

        label, ok = QInputDialog.getText(self, "Create Global OptionSet", "Display label:", text=name)
        if not ok or not label.strip():
            return
        label = label.strip()

        path, _ = QFileDialog.getOpenFileName(
            self, "Select options file (CSV / JSON)", "",
            "Data Files (*.csv *.json);;All Files (*)",
        )
        if not path:
            return

        try:
            options = load_options_from_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "File error", str(exc))
            return

        thread = QThread(self)
        worker = CreateGlobalWorker(self._svc, name, label, options)
        worker.log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.finished.connect(lambda ok: self._on_create_finished(ok, name))
        worker.finished.connect(thread.quit)
        self._start_worker(worker, thread)
        self._create_worker = worker

    def _on_create_finished(self, success: bool, name: str) -> None:
        if success:
            QMessageBox.information(self, "Success", f"OptionSet '{name}' created!")
            self._refresh_list()
        else:
            QMessageBox.warning(self, "Failed", f"Could not create '{name}'. See log.")

    # ═══════════════════════════════════════════════════════════
    #  Insert single option
    # ═══════════════════════════════════════════════════════════

    def _insert_single(self) -> None:
        if not self._ensure_connected():
            return
        name = self._ask_optionset_name("Insert Option – OptionSet")
        if not name:
            return
        label, ok = QInputDialog.getText(self, "Insert Option", "Option label:")
        if not ok or not label.strip():
            return
        val, ok = QInputDialog.getInt(self, "Insert Option", "Option value:", value=0)
        if not ok:
            return
        opt = OptionItem(label=label.strip(), value=val)

        thread = QThread(self)
        worker = InsertSingleWorker(self._svc, opt, name)
        worker.log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.finished.connect(lambda ok: self._on_insert_finished(ok, name))
        worker.finished.connect(thread.quit)
        self._start_worker(worker, thread)
        self._insert_worker = worker

    def _on_insert_finished(self, success: bool, name: str) -> None:
        if success:
            self._log(f"✅ Option inserted into '{name}'")
            self._fetch_options_remote(name)  # refresh right panel
        else:
            QMessageBox.warning(self, "Failed", "Insert failed. See log.")

    # ═══════════════════════════════════════════════════════════
    #  Bulk operations (insert / update / delete)
    # ═══════════════════════════════════════════════════════════

    def _bulk_op(self, operation: str) -> None:
        if not self._ensure_connected():
            return
        name = self._ask_optionset_name(f"Bulk {operation.title()} – OptionSet")
        if not name:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select file for bulk {operation}",
            "",
            "Data Files (*.csv *.json);;All Files (*)",
        )
        if not path:
            return

        try:
            options = load_options_from_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "File error", str(exc))
            return

        if not options:
            QMessageBox.information(self, "Empty", "No options found in file.")
            return

        # Progress dialog
        dlg = BulkProgressDialog(f"Bulk {operation.title()}", self)
        dlg.show()

        thread = QThread(self)
        worker = BulkOperationWorker(
            self._svc,
            options,
            name,
            operation,
            safe_insert=(operation == "insert"),
        )
        worker.log.connect(self._log)
        worker.log.connect(dlg.append_log)
        worker.batch_log.connect(dlg.append_log)
        worker.batch_log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.error.connect(dlg.append_log)
        worker.progress.connect(dlg.set_batch_progress)
        worker.finished.connect(lambda r: self._on_bulk_finished(r, operation, name, dlg))
        worker.finished.connect(thread.quit)

        dlg.cancel_requested.connect(thread.requestInterruption)

        self._start_worker(worker, thread)
        # prevent GC
        self._bulk_worker = worker
        self._bulk_dlg = dlg

    def _on_bulk_finished(self, report, operation: str, name: str, dlg: BulkProgressDialog) -> None:
        if report is not None:
            summary = (
                f"Bulk {operation} complete – "
                f"{report.succeeded}/{report.total} succeeded, "
                f"{report.failed} failed"
            )
        else:
            summary = f"Bulk {operation} returned no report."
        dlg.mark_finished(summary)
        self._refresh_list()
