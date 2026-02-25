"""
Background workers and business-logic controller.

All long-running Dataverse calls are executed in QThread workers so the
GUI stays responsive.  Workers emit signals that the MainWindow connects
to for updating the UI.
"""
from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from OptionSetHelper import (
    BatchReport,
    DataverseOptionSetService,
    OptionItem,
    create_service_from_env,
)

BATCH_SIZE = 50


# ── CSV / JSON loader (same logic as cli.py) ────────────────────────
def load_options_from_file(path: str) -> list[OptionItem]:
    ext = Path(path).suffix.lower()
    if ext == ".json":
        return _load_json(path)
    return _load_csv(path)


def _load_csv(path: str) -> list[OptionItem]:
    items: list[OptionItem] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample)
        except csv.Error:
            dialect = csv.excel
        has_header = sniffer.has_header(sample)
        reader = csv.reader(fh, dialect)
        if has_header:
            next(reader)
        for row in reader:
            if not row:
                continue
            row = [c.strip() for c in row]
            if len(row) >= 3:
                try:
                    val = int(row[0]); label = row[1]
                except ValueError:
                    try:
                        val = int(row[2]); label = row[1]
                    except ValueError:
                        continue
                items.append(OptionItem(label=label, value=val))
            elif len(row) == 2:
                try:
                    val = int(row[1]); label = row[0]
                except ValueError:
                    continue
                items.append(OptionItem(label=label, value=val))
            elif len(row) == 1:
                items.append(OptionItem(label=row[0], value=len(items)))
    return items


def _load_json(path: str) -> list[OptionItem]:
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    items: list[OptionItem] = []
    if isinstance(data, list):
        for e in data:
            items.append(OptionItem(label=e["label"], value=int(e["value"])))
    elif isinstance(data, dict):
        for label, value in data.items():
            items.append(OptionItem(label=label, value=int(value)))
    return items


# ═══════════════════════════════════════════════════════════════════
# Workers (run inside QThread)
# ═══════════════════════════════════════════════════════════════════

class AuthWorker(QObject):
    """Authenticate with Dataverse."""
    finished = Signal(object)       # DataverseOptionSetService | None
    error = Signal(str)
    log = Signal(str)

    def __init__(self, env_path: str):
        super().__init__()
        self.env_path = env_path

    def run(self) -> None:
        try:
            self.log.emit("Authenticating …")
            svc = create_service_from_env(self.env_path)
            svc.get_bearer_token()
            self.log.emit("✅ Authenticated successfully")
            self.finished.emit(svc)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(None)


class ListGlobalWorker(QObject):
    """Fetch all global OptionSets."""
    finished = Signal(list)
    error = Signal(str)
    log = Signal(str)

    def __init__(self, svc: DataverseOptionSetService):
        super().__init__()
        self.svc = svc

    def run(self) -> None:
        try:
            self.log.emit("Fetching global OptionSets …")
            data = self.svc.list_global_optionsets()
            self.log.emit(f"Received {len(data)} OptionSets")
            self.finished.emit(data)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit([])


class FetchOptionsWorker(QObject):
    """Fetch options for a single OptionSet."""
    finished = Signal(list)
    error = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        svc: DataverseOptionSetService,
        name: str,
        entity: str | None = None,
        attribute: str | None = None,
    ):
        super().__init__()
        self.svc = svc
        self.name = name
        self.entity = entity
        self.attribute = attribute

    def run(self) -> None:
        try:
            self.log.emit(f"Fetching options for '{self.name}' …")
            opts = self.svc.get_optionset_options(
                self.name,
                entity_logical_name=self.entity,
                attribute_logical_name=self.attribute,
            )
            self.log.emit(f"'{self.name}' has {len(opts)} option(s)")
            self.finished.emit(opts)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit([])


class CreateGlobalWorker(QObject):
    """Create a new global OptionSet."""
    finished = Signal(bool)
    error = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        svc: DataverseOptionSetService,
        name: str,
        display_label: str,
        options: list[OptionItem],
        language_code: int = 1033,
    ):
        super().__init__()
        self.svc = svc
        self.name = name
        self.display_label = display_label
        self.options = options
        self.language_code = language_code

    def run(self) -> None:
        try:
            self.log.emit(f"Creating global OptionSet '{self.name}' …")
            resp = self.svc.create_global_optionset(
                self.name, self.display_label, self.options, self.language_code,
            )
            self.log.emit(
                f"✅ Created '{self.name}' ({len(self.options)} options) – HTTP {resp.status_code}"
            )
            self.finished.emit(True)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(False)


class InsertSingleWorker(QObject):
    """Insert a single option."""
    finished = Signal(bool)
    error = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        svc: DataverseOptionSetService,
        option: OptionItem,
        optionset_name: str,
        language_code: int = 1033,
        entity: str | None = None,
        attribute: str | None = None,
    ):
        super().__init__()
        self.svc = svc
        self.option = option
        self.optionset_name = optionset_name
        self.language_code = language_code
        self.entity = entity
        self.attribute = attribute

    def run(self) -> None:
        try:
            self.log.emit(f"Inserting '{self.option.label}' = {self.option.value} …")
            resp = self.svc.insert_option(
                self.option,
                self.optionset_name,
                self.language_code,
                entity_logical_name=self.entity,
                attribute_logical_name=self.attribute,
            )
            self.log.emit(f"✅ Inserted – HTTP {resp.status_code}")
            self.finished.emit(True)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(False)


# ── Generic batched bulk worker ─────────────────────────────────────

class BulkOperationWorker(QObject):
    """
    Runs a bulk insert / update / delete in batches of BATCH_SIZE,
    refreshing the token at each batch.
    Emits progress and log signals.
    """
    progress = Signal(int, int)          # (current_batch, total_batches)
    batch_log = Signal(str)              # per-batch log line
    finished = Signal(object)            # final BatchReport
    error = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        svc: DataverseOptionSetService,
        options: list[OptionItem],
        optionset_name: str,
        operation: str,                  # "insert" | "update" | "delete"
        language_code: int = 1033,
        entity: str | None = None,
        attribute: str | None = None,
        safe_insert: bool = True,
        merge_labels: bool = False,
        continue_on_error: bool = True,
    ):
        super().__init__()
        self.svc = svc
        self.options = options
        self.optionset_name = optionset_name
        self.operation = operation
        self.language_code = language_code
        self.entity = entity
        self.attribute = attribute
        self.safe_insert = safe_insert
        self.merge_labels = merge_labels
        self.continue_on_error = continue_on_error

    def run(self) -> None:
        total = len(self.options)
        batch_indices = list(range(0, total, BATCH_SIZE))
        n_batches = len(batch_indices)

        all_results: list = []
        failed = 0
        succeeded = 0

        self.log.emit(
            f"Starting bulk {self.operation} – {total} option(s) in {n_batches} batch(es) of {BATCH_SIZE}"
        )

        def _noop(msg: str) -> None:
            pass

        for batch_num, i in enumerate(batch_indices, start=1):
            batch = self.options[i : i + BATCH_SIZE]
            start_dt = datetime.datetime.now()
            ts = start_dt.strftime("%Y-%m-%d %H:%M:%S")
            self.batch_log.emit(f"[{ts}] Batch {batch_num}/{n_batches} starting ({len(batch)} items)")

            # Refresh token
            try:
                self.svc.get_bearer_token()
            except Exception as exc:
                self.error.emit(f"Token refresh failed: {exc}")
                break

            try:
                report = self._run_batch(batch, _noop)
            except Exception as exc:
                self.error.emit(f"Batch {batch_num} failed: {exc}")
                if not self.continue_on_error:
                    break
                report = None

            end_dt = datetime.datetime.now()
            duration = (end_dt - start_dt).total_seconds()

            if report is not None:
                all_results.extend(report.results)
                failed += report.failed
                succeeded += report.succeeded

            self.batch_log.emit(
                f"[{end_dt.strftime('%Y-%m-%d %H:%M:%S')}] Batch {batch_num}/{n_batches} finished "
                f"(duration: {duration:.2f}s)"
            )
            self.progress.emit(batch_num, n_batches)

        final = BatchReport(
            results=all_results,
            total=total,
            succeeded=succeeded,
            failed=failed,
        )
        self.log.emit(
            f"Bulk {self.operation} complete – {succeeded}/{total} succeeded, {failed} failed"
        )
        self.finished.emit(final)

    # ── dispatch to the right service method ────────────────────
    def _run_batch(self, batch: list[OptionItem], cb: Any) -> BatchReport | None:
        if self.operation == "insert":
            if self.safe_insert:
                report, skipped = self.svc.safe_bulk_insert(
                    batch,
                    self.optionset_name,
                    self.language_code,
                    entity_logical_name=self.entity,
                    attribute_logical_name=self.attribute,
                    continue_on_error=self.continue_on_error,
                    progress_callback=cb,
                )
                if skipped:
                    self.batch_log.emit(f"  ⚠ Skipped {len(skipped)} duplicate(s)")
                return report  # may be None if all skipped
            else:
                return self.svc.bulk_insert_options(
                    batch,
                    self.optionset_name,
                    self.language_code,
                    entity_logical_name=self.entity,
                    attribute_logical_name=self.attribute,
                    continue_on_error=self.continue_on_error,
                    progress_callback=cb,
                )
        elif self.operation == "update":
            return self.svc.bulk_update_options(
                batch,
                self.optionset_name,
                self.language_code,
                merge_labels=self.merge_labels,
                entity_logical_name=self.entity,
                attribute_logical_name=self.attribute,
                continue_on_error=self.continue_on_error,
                progress_callback=cb,
            )
        elif self.operation == "delete":
            return self.svc.bulk_delete_options(
                batch,
                self.optionset_name,
                entity_logical_name=self.entity,
                attribute_logical_name=self.attribute,
                continue_on_error=self.continue_on_error,
                progress_callback=cb,
            )
        return None
