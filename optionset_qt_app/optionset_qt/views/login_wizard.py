"""
Microsoft interactive login wizard (MSAL device-code flow).

Responsibilities (SRP):
  - _DeviceFlowWorker: run MSAL device-code flow off the GUI thread
  - LoginWizardDialog: display the code / URL, react to auth events

Usage:
    dlg = LoginWizardDialog(parent, environment_url=..., tenant_id=..., client_id=...)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        provider = dlg.token_provider()  # MsalDeviceFlowProvider, ready for use
"""
from __future__ import annotations

import webbrowser
from typing import Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from optionset_qt.auth.token_providers import MsalDeviceFlowProvider


# ── Background worker ────────────────────────────────────────────────

class _DeviceFlowWorker(QObject):
    """Run the two-step MSAL device-code flow in a QThread."""

    flow_initiated = Signal(dict)   # emitted with {user_code, verification_uri, …}
    finished = Signal(str)          # emitted with the access token on success
    error = Signal(str)

    def __init__(self, provider: MsalDeviceFlowProvider) -> None:
        super().__init__()
        self._provider = provider

    def run(self) -> None:
        try:
            flow = self._provider.initiate_flow()
            self.flow_initiated.emit(flow)
            token = self._provider.acquire_token(flow)
            self.finished.emit(token)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Dialog ───────────────────────────────────────────────────────────

class LoginWizardDialog(QDialog):
    """
    Shows device-code instructions and waits for the user to authenticate.

    After ``exec()`` returns ``Accepted``, call ``token_provider()`` to get the
    authenticated ``MsalDeviceFlowProvider`` that can be passed to the service.
    """

    def __init__(
        self,
        parent=None,
        *,
        environment_url: str,
        tenant_id: str,
        client_id: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in with Microsoft")
        self.setMinimumWidth(500)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self._provider: Optional[MsalDeviceFlowProvider] = None
        self._verification_uri: str = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Status line
        self.lbl_status = QLabel("Connecting to Microsoft…")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        # Device code (large, bold)
        self.lbl_code = QLabel("")
        self.lbl_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_code.setStyleSheet(
            "font-size: 26px; font-weight: bold; letter-spacing: 6px;"
            "color: #0078d4; padding: 8px;"
        )
        layout.addWidget(self.lbl_code)

        # URL to visit
        self.lbl_url = QLabel("")
        self.lbl_url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_url.setOpenExternalLinks(True)
        layout.addWidget(self.lbl_url)

        # Instruction
        self.lbl_instruction = QLabel("")
        self.lbl_instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_instruction.setWordWrap(True)
        layout.addWidget(self.lbl_instruction)

        # Open browser button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_browser = QPushButton("Open Browser")
        self.btn_browser.setEnabled(False)
        self.btn_browser.clicked.connect(self._open_browser)
        btn_row.addWidget(self.btn_browser)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # OK / Cancel
        self._btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._btn_box.rejected.connect(self._on_cancel)
        layout.addWidget(self._btn_box)

        # Start auth
        scope = f"{environment_url.rstrip('/')}/.default"
        try:
            provider_instance = MsalDeviceFlowProvider(tenant_id, client_id, scope)
        except Exception as exc:
            self.lbl_status.setText(f"Failed to initialise MSAL: {exc}")
            return

        self._provider_instance = provider_instance
        self._thread = QThread(self)
        self._worker = _DeviceFlowWorker(provider_instance)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.flow_initiated.connect(self._on_flow_initiated)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    # ── slots ────────────────────────────────────────────────────────

    def _on_flow_initiated(self, flow: dict) -> None:
        user_code = flow.get("user_code", "")
        url = flow.get("verification_uri", "https://microsoft.com/devicelogin")
        self._verification_uri = url

        self.lbl_status.setText("Enter the code below at the Microsoft sign-in page:")
        self.lbl_code.setText(user_code)
        self.lbl_url.setText(f'<a href="{url}">{url}</a>')
        self.lbl_instruction.setText(
            "Sign in with your Microsoft 365 / Azure AD account. "
            "This window will close automatically when authentication is complete."
        )
        self.btn_browser.setEnabled(True)

    def _on_finished(self, _token: str) -> None:
        self._provider = self._provider_instance
        self.lbl_status.setText("✅ Signed in successfully!")
        self.lbl_code.clear()
        self.lbl_instruction.setText(
            "Click OK to apply these credentials and connect to Dataverse."
        )
        self.btn_browser.setEnabled(False)
        # Replace Cancel with OK
        self._btn_box.clear()
        ok_btn = self._btn_box.addButton(QDialogButtonBox.StandardButton.Ok)
        ok_btn.clicked.connect(self.accept)

    def _on_error(self, msg: str) -> None:
        self.lbl_status.setText(f"Authentication failed: {msg}")
        self.lbl_code.clear()
        self.btn_browser.setEnabled(False)

    def _open_browser(self) -> None:
        if self._verification_uri:
            webbrowser.open(self._verification_uri)

    def _on_cancel(self) -> None:
        if hasattr(self, "_thread") and self._thread.isRunning():
            # Detach signals so we silently ignore any late result
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
                self._worker.flow_initiated.disconnect()
            except RuntimeError:
                pass
        self.reject()

    # ── public API ───────────────────────────────────────────────────

    def token_provider(self) -> Optional[MsalDeviceFlowProvider]:
        """Return the authenticated provider, or None if auth wasn't completed."""
        return self._provider
