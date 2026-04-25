"""
MainWindow – glues the UI layout to the background workers.

All Dataverse calls run in a QThread so the GUI never blocks.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QSettings, QThread, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
)

from OptionSetHelper import DataverseOptionSetService, OptionItem, create_service_from_credentials

from optionset_qt.auth.credentials import AuthMethod, Credentials, parse_env_file
from optionset_qt.controllers.main_controller import (
    BulkOperationWorker,
    ClientCredentialsAuthWorker,
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

# QSettings keys
_K_TAB = "auth/active_tab"
_K_ENV_PATH = "auth/env_path"
_K_M_URL = "auth/manual/env_url"
_K_M_TENANT = "auth/manual/tenant_id"
_K_M_CLIENT = "auth/manual/client_id"
_K_M_SECRET = "auth/manual/client_secret"
_K_I_URL = "auth/interactive/env_url"
_K_I_TENANT = "auth/interactive/tenant_id"
_K_I_CLIENT = "auth/interactive/client_id"


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self) -> None:
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setup_ui(self)

        self._settings = QSettings("OptionSetHelper", "QtApp")
        self._svc: Optional[DataverseOptionSetService] = None
        self._optionset_infos: list[OptionSetInfo] = []   # full list from Dataverse
        self._displayed_infos: list[OptionSetInfo] = []   # what the table currently shows
        self._thread: Optional[QThread] = None

        self._connect_actions()
        self._auto_connect()

    # ═══════════════════════════════════════════════════════════
    #  Signal wiring
    # ═══════════════════════════════════════════════════════════

    def _connect_actions(self) -> None:
        ui = self.ui
        ui.action_settings.triggered.connect(self._open_settings)
        ui.action_quit.triggered.connect(self.close)
        ui.action_refresh.triggered.connect(self._refresh_list)
        ui.action_create_global.triggered.connect(self._create_global)
        ui.action_insert_single.triggered.connect(self._insert_single)
        ui.action_bulk_insert.triggered.connect(lambda: self._bulk_op("insert"))
        ui.action_bulk_update.triggered.connect(lambda: self._bulk_op("update"))
        ui.action_bulk_delete.triggered.connect(lambda: self._bulk_op("delete"))
        ui.tbl_optionsets.currentCellChanged.connect(self._on_optionset_selected)
        ui.btn_search.clicked.connect(self._filter_table)
        ui.search_input.returnPressed.connect(self._filter_table)

    # ═══════════════════════════════════════════════════════════
    #  Auto-connect on startup
    # ═══════════════════════════════════════════════════════════

    def _auto_connect(self) -> None:
        tab = int(self._settings.value(_K_TAB, 0))
        if tab == 0:
            env_path = self._settings.value(_K_ENV_PATH, "")
            # Fallback to legacy key
            if not env_path:
                env_path = self._settings.value("env_path", "")
            if env_path and Path(env_path).is_file():
                try:
                    creds = parse_env_file(env_path)
                    self._authenticate_with_credentials(creds)
                    return
                except Exception:
                    pass
        elif tab == 1:
            creds = self._load_manual_creds()
            if creds and creds.is_complete_for_client_credentials():
                self._authenticate_with_credentials(creds)
                return
        # Interactive (tab 2) or no saved credentials — prompt the user
        self._log("Open Settings (File → Settings) to configure your connection.")

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
            "Please configure your connection first (File → Settings).",
        )
        return False

    def _start_worker(self, worker, thread: QThread) -> None:
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
        if 0 <= row < len(self._displayed_infos):
            default = self._displayed_infos[row].name
        name, ok = QInputDialog.getText(self, title, "OptionSet name:", text=default)
        if ok and name.strip():
            return name.strip()
        return None

    # ── Credential persistence helpers ──────────────────────────────

    def _load_manual_creds(self) -> Credentials:
        return Credentials(
            environment_url=self._settings.value(_K_M_URL, ""),
            tenant_id=self._settings.value(_K_M_TENANT, ""),
            client_id=self._settings.value(_K_M_CLIENT, ""),
            client_secret=self._settings.value(_K_M_SECRET, ""),
        )

    def _load_interactive_creds(self) -> Credentials:
        return Credentials(
            environment_url=self._settings.value(_K_I_URL, ""),
            tenant_id=self._settings.value(_K_I_TENANT, ""),
            client_id=self._settings.value(_K_I_CLIENT, ""),
            auth_method=AuthMethod.INTERACTIVE,
        )

    def _save_settings(
        self,
        dlg: SettingsDialog,
        creds: Credentials,
    ) -> None:
        tab = dlg.active_tab()
        self._settings.setValue(_K_TAB, tab)
        if tab == 0:
            self._settings.setValue(_K_ENV_PATH, dlg.env_path())
            self._settings.setValue("env_path", dlg.env_path())  # legacy key
        elif tab == 1:
            url, tenant, client, secret = dlg.manual_values()
            self._settings.setValue(_K_M_URL, url)
            self._settings.setValue(_K_M_TENANT, tenant)
            self._settings.setValue(_K_M_CLIENT, client)
            self._settings.setValue(_K_M_SECRET, secret)
        else:
            url, tenant, client = dlg.interactive_values()
            self._settings.setValue(_K_I_URL, url)
            self._settings.setValue(_K_I_TENANT, tenant)
            self._settings.setValue(_K_I_CLIENT, client)

    # ═══════════════════════════════════════════════════════════
    #  Settings / Authentication
    # ═══════════════════════════════════════════════════════════

    def _open_settings(self) -> None:
        tab = int(self._settings.value(_K_TAB, 0))
        dlg = SettingsDialog(
            self,
            env_path=self._settings.value(_K_ENV_PATH, self._settings.value("env_path", "")),
            manual_creds=self._load_manual_creds(),
            interactive_creds=self._load_interactive_creds(),
            active_tab=tab,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        creds = dlg.credentials()
        if not creds:
            return

        self._save_settings(dlg, creds)

        provider = dlg.token_provider()
        if provider is not None:
            self._authenticate_with_provider(creds, provider)
        else:
            self._authenticate_with_credentials(creds)

    def _authenticate_with_credentials(self, creds: Credentials) -> None:
        self._status("Authenticating …")
        thread = QThread(self)
        worker = ClientCredentialsAuthWorker(creds)
        worker.log.connect(self._log)
        worker.error.connect(lambda e: self._log(f"❌ {e}"))
        worker.finished.connect(self._on_auth_finished)
        worker.finished.connect(thread.quit)
        self._start_worker(worker, thread)
        self._auth_worker = worker  # prevent GC

    def _authenticate_with_provider(
        self, creds: Credentials, provider: Callable[[], str]
    ) -> None:
        self._status("Connecting …")
        try:
            svc = create_service_from_credentials(creds, token_provider=provider)
            self._log("✅ Authenticated via Microsoft Login")
            self._on_auth_finished(svc)
        except Exception as exc:
            self._log(f"❌ {exc}")
            self._status("Authentication failed")

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
        self._displayed_infos = infos  # keep in sync so row indices always match
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

    def _on_optionset_selected(
        self, row: int, _col: int, _prev_row: int, _prev_col: int
    ) -> None:
        if row < 0 or row >= len(self._displayed_infos):
            return
        info = self._displayed_infos[row]
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
        label, ok = QInputDialog.getText(
            self, "Create Global OptionSet", "Display label:", text=name
        )
        if not ok or not label.strip():
            return
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
        worker = CreateGlobalWorker(self._svc, name, label.strip(), options)
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
            self._fetch_options_remote(name)
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
            self, f"Select file for bulk {operation}", "",
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

        dlg = BulkProgressDialog(f"Bulk {operation.title()}", self)
        dlg.show()

        thread = QThread(self)
        worker = BulkOperationWorker(
            self._svc, options, name, operation,
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
        self._bulk_worker = worker
        self._bulk_dlg = dlg

    def _on_bulk_finished(
        self, report, operation: str, name: str, dlg: BulkProgressDialog
    ) -> None:
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
