"""Settings dialog – configure .env path and review connection info."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """Modal dialog to select a .env file and preview the settings."""

    def __init__(self, parent=None, current_env_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setMinimumWidth(520)

        self._env_path = current_env_path

        layout = QVBoxLayout(self)

        # ── .env file path ──────────────────────────────────
        env_group = QGroupBox("Environment file (.env)")
        env_layout = QHBoxLayout(env_group)

        self.txt_env_path = QLineEdit(current_env_path)
        self.txt_env_path.setPlaceholderText("Path to .env file …")
        env_layout.addWidget(self.txt_env_path, stretch=1)

        btn_browse = QPushButton("Browse …")
        btn_browse.clicked.connect(self._browse_env)
        env_layout.addWidget(btn_browse)

        layout.addWidget(env_group)

        # ── Preview fields ──────────────────────────────────
        preview_group = QGroupBox("Connection preview")
        form = QFormLayout(preview_group)

        self.lbl_env_url = QLineEdit()
        self.lbl_env_url.setReadOnly(True)
        self.lbl_tenant = QLineEdit()
        self.lbl_tenant.setReadOnly(True)
        self.lbl_client = QLineEdit()
        self.lbl_client.setReadOnly(True)
        self.lbl_secret = QLineEdit()
        self.lbl_secret.setReadOnly(True)
        self.lbl_secret.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Environment URL:", self.lbl_env_url)
        form.addRow("Tenant ID:", self.lbl_tenant)
        form.addRow("Client ID:", self.lbl_client)
        form.addRow("Client Secret:", self.lbl_secret)

        layout.addWidget(preview_group)

        # ── Status label ────────────────────────────────────
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        # ── Dialog buttons ──────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Load preview if path already set
        if current_env_path:
            self._load_preview(current_env_path)

        self.txt_env_path.textChanged.connect(self._load_preview)

    # ── helpers ─────────────────────────────────────────────
    def _browse_env(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select .env file", "", "Environment Files (*.env);;All Files (*)"
        )
        if path:
            self.txt_env_path.setText(path)

    def _load_preview(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            self.lbl_status.setText("⚠ File not found")
            self._clear_preview()
            return
        try:
            data = self._parse_env(p)
            self.lbl_env_url.setText(data.get("environmentUrl", ""))
            self.lbl_tenant.setText(data.get("tenant_id", ""))
            self.lbl_client.setText(data.get("client_id", ""))
            self.lbl_secret.setText(data.get("client_secret", ""))
            self.lbl_status.setText("✅ .env loaded")
        except Exception as exc:
            self.lbl_status.setText(f"❌ {exc}")
            self._clear_preview()

    def _clear_preview(self) -> None:
        for w in (self.lbl_env_url, self.lbl_tenant, self.lbl_client, self.lbl_secret):
            w.clear()

    @staticmethod
    def _parse_env(path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip("\"'")
        return result

    # ── public API ──────────────────────────────────────────
    def env_path(self) -> str:
        return self.txt_env_path.text().strip()
