"""
Settings dialog — three ways to configure connection credentials.

  Tab 0 – Environment File  : browse for a .env file (existing behaviour)
  Tab 1 – Manual Entry      : type credentials directly (all fields editable)
  Tab 2 – Microsoft Login   : interactive MSAL device-code sign-in (no secret needed)

SRP: each tab is its own QWidget subclass with a single responsibility.
The outer SettingsDialog only aggregates them and returns the result.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from optionset_qt.auth.credentials import AuthMethod, Credentials, parse_env_file


# ═══════════════════════════════════════════════════════════
#  Tab 0 – Environment File
# ═══════════════════════════════════════════════════════════

class _EnvFileTab(QWidget):
    """Browse for a .env file and preview its contents."""

    def __init__(self, env_path: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        # Path row
        file_group = QGroupBox("Environment file (.env)")
        path_row = QHBoxLayout(file_group)
        self.txt_path = QLineEdit(env_path)
        self.txt_path.setPlaceholderText("Path to .env file …")
        path_row.addWidget(self.txt_path, stretch=1)
        btn_browse = QPushButton("Browse …")
        btn_browse.clicked.connect(self._browse)
        path_row.addWidget(btn_browse)
        layout.addWidget(file_group)

        # Preview (read-only)
        preview_group = QGroupBox("Connection preview")
        form = QFormLayout(preview_group)

        self._fld_url = self._ro_field()
        self._fld_tenant = self._ro_field()
        self._fld_client = self._ro_field()
        self._fld_secret = self._ro_field(password=True)

        form.addRow("Environment URL:", self._fld_url)
        form.addRow("Tenant ID:", self._fld_tenant)
        form.addRow("Client ID:", self._fld_client)
        form.addRow("Client Secret:", self._fld_secret)
        layout.addWidget(preview_group)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

        self.txt_path.textChanged.connect(self._load_preview)
        if env_path:
            self._load_preview(env_path)

    @staticmethod
    def _ro_field(*, password: bool = False) -> QLineEdit:
        f = QLineEdit()
        f.setReadOnly(True)
        if password:
            f.setEchoMode(QLineEdit.EchoMode.Password)
        return f

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select .env file", "", "Environment Files (*.env);;All Files (*)"
        )
        if path:
            self.txt_path.setText(path)

    def _load_preview(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            self.lbl_status.setText("⚠ File not found")
            for f in (self._fld_url, self._fld_tenant, self._fld_client, self._fld_secret):
                f.clear()
            return
        try:
            creds = parse_env_file(path)
            self._fld_url.setText(creds.environment_url)
            self._fld_tenant.setText(creds.tenant_id)
            self._fld_client.setText(creds.client_id)
            self._fld_secret.setText(creds.client_secret)
            self.lbl_status.setText("✅ .env loaded")
        except Exception as exc:
            self.lbl_status.setText(f"❌ {exc}")

    def get_credentials(self) -> Optional[Credentials]:
        path = self.txt_path.text().strip()
        if not path or not Path(path).is_file():
            self.lbl_status.setText("⚠ Please select a valid .env file")
            return None
        try:
            return parse_env_file(path)
        except Exception as exc:
            self.lbl_status.setText(f"❌ {exc}")
            return None

    def env_path(self) -> str:
        return self.txt_path.text().strip()


# ═══════════════════════════════════════════════════════════
#  Tab 1 – Manual Entry
# ═══════════════════════════════════════════════════════════

class _ManualTab(QWidget):
    """Editable form for all four credential fields."""

    def __init__(self, creds: Credentials) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        group = QGroupBox("Dataverse credentials")
        form = QFormLayout(group)

        self.txt_url = QLineEdit(creds.environment_url)
        self.txt_url.setPlaceholderText("https://yourorg.crm4.dynamics.com/")
        self.txt_tenant = QLineEdit(creds.tenant_id)
        self.txt_tenant.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        self.txt_client = QLineEdit(creds.client_id)
        self.txt_client.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

        # Secret field with show/hide toggle
        secret_row = QHBoxLayout()
        self.txt_secret = QLineEdit(creds.client_secret)
        self.txt_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_secret.setPlaceholderText("Client secret …")
        self.chk_show = QCheckBox("Show")
        self.chk_show.toggled.connect(self._toggle_secret)
        secret_row.addWidget(self.txt_secret, stretch=1)
        secret_row.addWidget(self.chk_show)

        form.addRow("Environment URL *:", self.txt_url)
        form.addRow("Tenant ID *:", self.txt_tenant)
        form.addRow("Client ID *:", self.txt_client)
        form.addRow("Client Secret *:", secret_row)

        layout.addWidget(group)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def _toggle_secret(self, show: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self.txt_secret.setEchoMode(mode)

    def get_credentials(self) -> Optional[Credentials]:
        url = self.txt_url.text().strip()
        tenant = self.txt_tenant.text().strip()
        client = self.txt_client.text().strip()
        secret = self.txt_secret.text().strip()

        missing = [
            name for name, val in [
                ("Environment URL", url), ("Tenant ID", tenant),
                ("Client ID", client), ("Client Secret", secret),
            ]
            if not val
        ]
        if missing:
            self.lbl_status.setText(f"⚠ Missing: {', '.join(missing)}")
            return None
        self.lbl_status.clear()
        return Credentials(
            environment_url=url,
            tenant_id=tenant,
            client_id=client,
            client_secret=secret,
            auth_method=AuthMethod.CLIENT_CREDENTIALS,
        )

    def values(self) -> tuple[str, str, str, str]:
        return (
            self.txt_url.text().strip(),
            self.txt_tenant.text().strip(),
            self.txt_client.text().strip(),
            self.txt_secret.text().strip(),
        )


# ═══════════════════════════════════════════════════════════
#  Tab 2 – Microsoft Interactive Login
# ═══════════════════════════════════════════════════════════

class _InteractiveTab(QWidget):
    """MSAL device-code flow — no client secret required."""

    def __init__(self, creds: Credentials) -> None:
        super().__init__()
        self._token_provider: Optional[Callable[[], str]] = None

        layout = QVBoxLayout(self)

        info = QLabel(
            "Sign in with your Microsoft 365 account.\n"
            "No client secret is needed — a login wizard will open and guide you."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        group = QGroupBox("Dataverse environment")
        form = QFormLayout(group)

        self.txt_url = QLineEdit(creds.environment_url)
        self.txt_url.setPlaceholderText("https://yourorg.crm4.dynamics.com/")
        self.txt_tenant = QLineEdit(creds.tenant_id)
        self.txt_tenant.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  (or 'common')")
        self.txt_client = QLineEdit(creds.client_id)
        self.txt_client.setPlaceholderText("Azure AD app (public client) client ID")

        form.addRow("Environment URL *:", self.txt_url)
        form.addRow("Tenant ID *:", self.txt_tenant)
        form.addRow("Client ID *:", self.txt_client)
        layout.addWidget(group)

        btn_row = QHBoxLayout()
        self.btn_sign_in = QPushButton("Sign in with Microsoft …")
        self.btn_sign_in.clicked.connect(self._start_wizard)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_sign_in)
        layout.addLayout(btn_row)

        self.lbl_status = QLabel("Not signed in.")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        layout.addStretch()

    def _start_wizard(self) -> None:
        url = self.txt_url.text().strip()
        tenant = self.txt_tenant.text().strip()
        client = self.txt_client.text().strip()
        missing = [n for n, v in [("URL", url), ("Tenant ID", tenant), ("Client ID", client)] if not v]
        if missing:
            self.lbl_status.setText(f"⚠ Please fill in: {', '.join(missing)}")
            return

        from optionset_qt.views.login_wizard import LoginWizardDialog
        dlg = LoginWizardDialog(
            self,
            environment_url=url,
            tenant_id=tenant,
            client_id=client,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            provider = dlg.token_provider()
            if provider is not None:
                self._token_provider = provider
                self.lbl_status.setText("✅ Signed in — click OK to connect")
                self.btn_sign_in.setText("Sign in again …")
            else:
                self.lbl_status.setText("⚠ Sign-in did not complete")
        else:
            self.lbl_status.setText("Sign-in cancelled.")

    def get_credentials(self) -> Optional[Credentials]:
        if self._token_provider is None:
            self.lbl_status.setText("⚠ Please sign in first (click 'Sign in with Microsoft …')")
            return None
        return Credentials(
            environment_url=self.txt_url.text().strip(),
            tenant_id=self.txt_tenant.text().strip(),
            client_id=self.txt_client.text().strip(),
            auth_method=AuthMethod.INTERACTIVE,
        )

    def get_token_provider(self) -> Optional[Callable[[], str]]:
        return self._token_provider

    def values(self) -> tuple[str, str, str]:
        return (
            self.txt_url.text().strip(),
            self.txt_tenant.text().strip(),
            self.txt_client.text().strip(),
        )


# ═══════════════════════════════════════════════════════════
#  Main dialog
# ═══════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """
    Three-tab connection settings dialog.

    After exec() returns Accepted:
      • credentials()     → Credentials dataclass
      • token_provider()  → callable (only set for interactive / MSAL tab)
      • active_tab()      → int (0/1/2), for persisting the last-used tab
      • env_path()        → str (only meaningful when tab 0 is active)
    """

    def __init__(
        self,
        parent=None,
        *,
        env_path: str = "",
        manual_creds: Optional[Credentials] = None,
        interactive_creds: Optional[Credentials] = None,
        active_tab: int = 0,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setMinimumWidth(560)

        self._result_credentials: Optional[Credentials] = None
        self._result_token_provider: Optional[Callable[[], str]] = None

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tab_env = _EnvFileTab(env_path)
        self._tab_manual = _ManualTab(manual_creds or Credentials())
        self._tab_interactive = _InteractiveTab(
            interactive_creds or Credentials(auth_method=AuthMethod.INTERACTIVE)
        )
        self._tabs.addTab(self._tab_env, "Environment File")
        self._tabs.addTab(self._tab_manual, "Manual Entry")
        self._tabs.addTab(self._tab_interactive, "Microsoft Login")
        self._tabs.setCurrentIndex(max(0, min(active_tab, 2)))
        layout.addWidget(self._tabs)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_accept(self) -> None:
        idx = self._tabs.currentIndex()
        if idx == 0:
            creds = self._tab_env.get_credentials()
            provider = None
        elif idx == 1:
            creds = self._tab_manual.get_credentials()
            provider = None
        else:
            creds = self._tab_interactive.get_credentials()
            provider = self._tab_interactive.get_token_provider()

        if creds is None:
            return  # validation failed; keep dialog open
        self._result_credentials = creds
        self._result_token_provider = provider
        self.accept()

    # ── public API ───────────────────────────────────────────────────

    def credentials(self) -> Optional[Credentials]:
        return self._result_credentials

    def token_provider(self) -> Optional[Callable[[], str]]:
        return self._result_token_provider

    def active_tab(self) -> int:
        return self._tabs.currentIndex()

    def env_path(self) -> str:
        return self._tab_env.env_path()

    def manual_values(self) -> tuple[str, str, str, str]:
        return self._tab_manual.values()

    def interactive_values(self) -> tuple[str, str, str]:
        return self._tab_interactive.values()
