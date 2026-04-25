"""
Credentials data model, AuthMethod enum, and .env file parser.

Single Responsibility: this module only holds credential *data*.
All authentication *behaviour* lives in token_providers.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class AuthMethod(Enum):
    """Which authentication strategy to use."""
    CLIENT_CREDENTIALS = "client_credentials"   # app client_id + client_secret
    INTERACTIVE = "interactive"                 # MSAL device-code / browser flow


@dataclass
class Credentials:
    """All parameters needed to connect to a Dataverse environment."""
    environment_url: str = ""
    tenant_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    auth_method: AuthMethod = AuthMethod.CLIENT_CREDENTIALS

    def is_complete_for_client_credentials(self) -> bool:
        return bool(self.environment_url and self.tenant_id and self.client_id and self.client_secret)

    def is_complete_for_interactive(self) -> bool:
        return bool(self.environment_url and self.tenant_id and self.client_id)


def parse_env_file(path: str) -> Credentials:
    """Parse a .env file and return a Credentials object."""
    data: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip("\"'")
    return Credentials(
        environment_url=data.get("environmentUrl", ""),
        tenant_id=data.get("tenant_id", ""),
        client_id=data.get("client_id", ""),
        client_secret=data.get("client_secret", ""),
    )
