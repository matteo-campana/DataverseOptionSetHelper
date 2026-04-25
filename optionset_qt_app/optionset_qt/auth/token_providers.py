"""
Token-provider strategy implementations.

Each provider is a callable() -> str that returns a valid Bearer token.
DataverseOptionSetService accepts any such callable, satisfying DIP:
high-level service code depends on the abstraction (callable), not concrete classes.

OCP: adding a new auth method (e.g. certificate, managed identity) does not
modify existing providers or the service.
"""
from __future__ import annotations

import time
from typing import Optional

import requests


class ClientCredentialsProvider:
    """
    OAuth2 client-credentials flow.
    Caches the token and reuses it until 60 s before expiry.
    """

    _SAFETY_MARGIN = 60  # seconds

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._token: Optional[str] = None
        self._expiry: float = 0.0

    def __call__(self) -> str:
        now = time.time()
        if self._token and now < self._expiry:
            return self._token
        url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
        resp = requests.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self._scope,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._expiry = now + int(body.get("expires_in", 3600)) - self._SAFETY_MARGIN
        return self._token  # type: ignore[return-value]


class MsalDeviceFlowProvider:
    """
    MSAL public-client device-code flow.
    Token caching and silent refresh are handled by the MSAL library.

    Usage:
        provider = MsalDeviceFlowProvider(tenant_id, client_id, scope)
        flow = provider.initiate_flow()        # → show user_code + URL
        token = provider.acquire_token(flow)   # → blocks until user signs in
        # After that, provider() returns tokens silently.
    """

    def __init__(self, tenant_id: str, client_id: str, scope: str) -> None:
        import msal  # deferred import – not everyone needs MSAL
        self._scope = [scope]
        self._app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        self._account = None

    def initiate_flow(self) -> dict:
        """Start the device-code flow. Returns the flow dict (contains user_code, verification_uri)."""
        flow = self._app.initiate_device_flow(scopes=self._scope)
        if "user_code" not in flow:
            raise RuntimeError(flow.get("error_description", "Failed to initiate device flow"))
        return flow

    def acquire_token(self, flow: dict) -> str:
        """Block until the user completes sign-in. Returns the access token."""
        result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description", "Microsoft authentication failed"))
        accounts = self._app.get_accounts()
        self._account = accounts[0] if accounts else None
        return result["access_token"]

    def __call__(self) -> str:
        """Silent token refresh for subsequent service calls after initial login."""
        if self._account:
            result = self._app.acquire_token_silent(self._scope, account=self._account)
            if result and "access_token" in result:
                return result["access_token"]
        raise RuntimeError(
            "Interactive session expired. Please sign in again via File → Settings."
        )
