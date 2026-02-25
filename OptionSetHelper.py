"""
Dataverse OptionSet Helper Service
===================================
A general-purpose service for managing Dataverse OptionSets (global & local).
Supports: Create, Read/List, Insert, Update, Delete (single & batch).
Authentication via OAuth2 client credentials flow with token caching.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("OptionSetHelper")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class OptionItem:
    """Represents a single option (label + integer value) in an OptionSet."""
    label: str
    value: int

    def to_insert_payload(
        self,
        option_set_name: str,
        language_code: int = 1033,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> dict:
        """Return the JSON body for an InsertOptionValue call."""
        payload: dict[str, Any] = {
            "Label": {
                "LocalizedLabels": [
                    {"Label": self.label, "LanguageCode": language_code}
                ]
            },
            "Value": self.value,
        }
        if entity_logical_name and attribute_logical_name:
            payload["EntityLogicalName"] = entity_logical_name
            payload["AttributeLogicalName"] = attribute_logical_name
        else:
            payload["OptionSetName"] = option_set_name
        return payload

    def to_update_payload(
        self,
        option_set_name: str,
        language_code: int = 1033,
        merge_labels: bool = False,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> dict:
        """Return the JSON body for an UpdateOptionValue call."""
        payload: dict[str, Any] = {
            "Label": {
                "LocalizedLabels": [
                    {"Label": self.label, "LanguageCode": language_code}
                ]
            },
            "Value": self.value,
            "MergeLabels": merge_labels,
        }
        if entity_logical_name and attribute_logical_name:
            payload["EntityLogicalName"] = entity_logical_name
            payload["AttributeLogicalName"] = attribute_logical_name
        else:
            payload["OptionSetName"] = option_set_name
        return payload

    def to_delete_payload(
        self,
        option_set_name: str,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> dict:
        """Return the JSON body for a DeleteOptionValue call."""
        payload: dict[str, Any] = {"Value": self.value}
        if entity_logical_name and attribute_logical_name:
            payload["EntityLogicalName"] = entity_logical_name
            payload["AttributeLogicalName"] = attribute_logical_name
        else:
            payload["OptionSetName"] = option_set_name
        return payload

    def to_option_metadata(self, language_code: int = 1033) -> dict:
        """Return the OptionMetadata shape used in the POST create body."""
        return {
            "@odata.type": "Microsoft.Dynamics.CRM.OptionMetadata",
            "Label": {
                "LocalizedLabels": [
                    {"Label": self.label, "LanguageCode": language_code}
                ]
            },
            "Value": self.value,
        }


@dataclass
class BatchResult:
    """Outcome of a single sub-request inside a $batch."""
    index: int
    label: str
    value: int
    status_code: int
    success: bool
    detail: str = ""


@dataclass
class BatchReport:
    """Aggregated outcome of a $batch call."""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[BatchResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class DataverseOptionSetService:
    """General-purpose Dataverse OptionSet management service."""

    API_VERSION = "v9.2"

    def __init__(
        self,
        environment_url: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ):
        self.environment_url = environment_url.rstrip("/")
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret

        self._token: str | None = None
        self._token_expiry: float = 0.0  # epoch seconds

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def get_bearer_token(self, *, force_new: bool = False) -> str:
        """
        Obtain a Bearer token via OAuth2 client-credentials.

        * Cached token is reused if still valid (with 60 s margin).
        * ``force_new=True`` always fetches a fresh token (use for batch).
        """
        now = time.time()
        if not force_new and self._token and now < self._token_expiry:
            logger.debug("Reusing cached token (expires in %.0f s)", self._token_expiry - now)
            return self._token

        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": f"{self.environment_url}/.default",
        }
        resp = requests.post(token_url, data=data, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        # Cache with a 60 s safety margin
        self._token_expiry = now + int(body.get("expires_in", 3600)) - 60
        logger.debug("Obtained new bearer token")
        return self._token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @property
    def _base_url(self) -> str:
        return f"{self.environment_url}/api/data/{self.API_VERSION}"

    def _headers(self, *, content_type: str = "application/json; charset=utf-8") -> dict:
        return {
            "Authorization": f"Bearer {self.get_bearer_token()}",
            "Content-Type": content_type,
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }

    # ------------------------------------------------------------------
    # READ / LIST
    # ------------------------------------------------------------------
    def get_global_optionset(self, name: str) -> dict | None:
        """Retrieve a global OptionSet definition by its schema name."""
        url = f"{self._base_url}/GlobalOptionSetDefinitions(Name='{name}')"
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def list_global_optionsets(self) -> list[dict]:
        """List all global OptionSet definitions."""
        url = f"{self._base_url}/GlobalOptionSetDefinitions"
        resp = requests.get(url, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.json().get("value", [])

    def search_global_optionsets_by_label(
        self, search_text: str, language_code: int = 1033
    ) -> list[dict]:
        """
        Return global OptionSets whose *DisplayName* contains ``search_text``
        (case-insensitive substring match done client-side because the
        Dataverse OData endpoint doesn't support $filter on
        DisplayName directly).
        """
        all_sets = self.list_global_optionsets()
        results = []
        for os_def in all_sets:
            display = os_def.get("DisplayName", {})
            localized = display.get("LocalizedLabels", [])
            for lbl in localized:
                if (
                    lbl.get("LanguageCode") == language_code
                    and search_text.lower() in lbl.get("Label", "").lower()
                ):
                    results.append(os_def)
                    break
        return results

    def get_local_optionset(
        self, entity_logical_name: str, attribute_logical_name: str
    ) -> dict | None:
        """Retrieve a local (entity-scoped) OptionSet attribute definition."""
        url = (
            f"{self._base_url}/EntityDefinitions(LogicalName='{entity_logical_name}')"
            f"/Attributes(LogicalName='{attribute_logical_name}')"
            f"/Microsoft.Dynamics.CRM.PicklistAttributeMetadata"
            f"?$expand=OptionSet"
        )
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_optionset_options(
        self,
        option_set_name: str,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> list[dict]:
        """
        Return the current options of a global or local OptionSet.
        Useful for duplicate detection before insert.
        """
        if entity_logical_name and attribute_logical_name:
            data = self.get_local_optionset(entity_logical_name, attribute_logical_name)
            if not data:
                return []
            return data.get("OptionSet", {}).get("Options", [])
        else:
            data = self.get_global_optionset(option_set_name)
            if not data:
                return []
            return data.get("Options", [])

    def get_existing_values(
        self,
        option_set_name: str,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> set[int]:
        """Return a set of all existing option *Values* for fast lookup."""
        options = self.get_optionset_options(
            option_set_name,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
        )
        return {opt["Value"] for opt in options if "Value" in opt}

    def get_existing_labels(
        self,
        option_set_name: str,
        language_code: int = 1033,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> dict[str, int]:
        """
        Return a mapping ``{label: value}`` of all existing options.
        Useful for duplicate detection by label.
        """
        options = self.get_optionset_options(
            option_set_name,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
        )
        result: dict[str, int] = {}
        for opt in options:
            lbl_data = opt.get("Label", {}).get("LocalizedLabels", [])
            for lbl in lbl_data:
                if lbl.get("LanguageCode") == language_code:
                    result[lbl["Label"]] = opt["Value"]
        return result

    # ------------------------------------------------------------------
    # CREATE global OptionSet
    # ------------------------------------------------------------------
    def create_global_optionset(
        self,
        name: str,
        display_label: str,
        options: list[OptionItem],
        language_code: int = 1033,
        *,
        is_custom: bool = True,
        option_set_type: str = "Picklist",
    ) -> requests.Response:
        """
        POST /GlobalOptionSetDefinitions to create a brand-new global OptionSet.
        """
        url = f"{self._base_url}/GlobalOptionSetDefinitions"
        body = {
            "@odata.type": "Microsoft.Dynamics.CRM.OptionSetMetadata",
            "Name": name,
            "DisplayName": {
                "LocalizedLabels": [
                    {"Label": display_label, "LanguageCode": language_code}
                ]
            },
            "IsCustomOptionSet": is_custom,
            "OptionSetType": option_set_type,
            "Options": [o.to_option_metadata(language_code) for o in options],
        }
        resp = requests.post(
            url,
            headers=self._headers(),
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # Single-record operations
    # ------------------------------------------------------------------
    def insert_option(
        self,
        option: OptionItem,
        option_set_name: str,
        language_code: int = 1033,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> requests.Response:
        """POST InsertOptionValue – single option."""
        url = f"{self._base_url}/InsertOptionValue"
        payload = option.to_insert_payload(
            option_set_name,
            language_code,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
        )
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp

    def update_option(
        self,
        option: OptionItem,
        option_set_name: str,
        language_code: int = 1033,
        merge_labels: bool = False,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> requests.Response:
        """POST UpdateOptionValue – single option."""
        url = f"{self._base_url}/UpdateOptionValue"
        payload = option.to_update_payload(
            option_set_name,
            language_code,
            merge_labels,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
        )
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp

    def delete_option(
        self,
        option: OptionItem,
        option_set_name: str,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
    ) -> requests.Response:
        """POST DeleteOptionValue – single option."""
        url = f"{self._base_url}/DeleteOptionValue"
        payload = option.to_delete_payload(
            option_set_name,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
        )
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp

    # ------------------------------------------------------------------
    # $batch helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_batch_body(
        action: str,
        payloads: list[dict],
        boundary: str,
    ) -> str:
        """
        Build an OData $batch multipart body.

        ``action`` is one of: InsertOptionValue, UpdateOptionValue,
        DeleteOptionValue.
        """
        CRLF = "\r\n"
        lines: list[str] = []
        lines.append(f"--{boundary}")
        lines.append("Content-Type: multipart/mixed;boundary=changeset_001")
        lines.append("")

        for idx, payload in enumerate(payloads):
            lines.append("--changeset_001")
            lines.append("Content-Type: application/http")
            lines.append("Content-Transfer-Encoding: binary")
            lines.append(f"Content-ID: {idx + 1}")
            lines.append("")
            lines.append(f"POST {action} HTTP/1.1")
            lines.append("Content-Type: application/json; charset=utf-8")
            lines.append("")
            lines.append(json.dumps(payload))
            lines.append("")

        lines.append("--changeset_001--")
        lines.append(f"--{boundary}--")
        return CRLF.join(lines)

    @staticmethod
    def _parse_batch_response(
        response_text: str,
        options: list[OptionItem],
    ) -> BatchReport:
        """
        Best-effort parse of the multipart $batch response.
        Returns a BatchReport with per-item outcomes.
        """
        report = BatchReport(total=len(options))

        # Each sub-response is delimited by a boundary and contains an HTTP
        # status line like "HTTP/1.1 204 No Content" or "HTTP/1.1 400 …"
        parts = response_text.split("--changesetresponse_")
        result_idx = 0
        for part in parts:
            # find the HTTP status line
            for line in part.splitlines():
                stripped = line.strip()
                if stripped.startswith("HTTP/1.1"):
                    tokens = stripped.split(" ", 2)
                    code = int(tokens[1]) if len(tokens) > 1 else 0
                    detail = tokens[2] if len(tokens) > 2 else ""
                    success = 200 <= code < 300
                    opt = (
                        options[result_idx]
                        if result_idx < len(options)
                        else OptionItem(label="?", value=-1)
                    )
                    br = BatchResult(
                        index=result_idx,
                        label=opt.label,
                        value=opt.value,
                        status_code=code,
                        success=success,
                        detail=detail,
                    )
                    report.results.append(br)
                    if success:
                        report.succeeded += 1
                    else:
                        report.failed += 1
                    result_idx += 1
                    break

        # If we couldn't parse individual results, estimate from HTTP status
        if not report.results:
            report.succeeded = report.total  # optimistic
        return report

    # ------------------------------------------------------------------
    # Batch operations (with progress callback)
    # ------------------------------------------------------------------
    def bulk_insert_options(
        self,
        options: list[OptionItem],
        option_set_name: str,
        language_code: int = 1033,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
        continue_on_error: bool = False,
        progress_callback: Any = None,
    ) -> BatchReport:
        """
        $batch InsertOptionValue for many options at once.
        Always requests a **new** token before the batch call.
        """
        # Fresh token for batch
        self.get_bearer_token(force_new=True)

        payloads = []
        for opt in options:
            payloads.append(
                opt.to_insert_payload(
                    option_set_name,
                    language_code,
                    entity_logical_name=entity_logical_name,
                    attribute_logical_name=attribute_logical_name,
                )
            )

        boundary = f"batch_{int(time.time() * 1000)}"
        body = self._build_batch_body("InsertOptionValue", payloads, boundary)

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": f"multipart/mixed;boundary={boundary}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        if continue_on_error:
            headers["Prefer"] = "odata.continue-on-error"

        if progress_callback:
            progress_callback(f"Sending batch INSERT for {len(options)} options …")

        resp = requests.post(
            f"{self._base_url}/$batch",
            headers=headers,
            data=body.encode("utf-8"),
            timeout=300,
        )
        try:
            resp.raise_for_status()
        except Exception:
            print("Batch request body:\n", body)
            print("Batch response:\n", resp.text)
            raise

        report = self._parse_batch_response(resp.text, options)
        if progress_callback:
            progress_callback(
                f"Batch INSERT complete: {report.succeeded}/{report.total} succeeded"
            )
        return report

    def bulk_update_options(
        self,
        options: list[OptionItem],
        option_set_name: str,
        language_code: int = 1033,
        merge_labels: bool = False,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
        continue_on_error: bool = False,
        progress_callback: Any = None,
    ) -> BatchReport:
        """
        $batch UpdateOptionValue for many options at once.
        Always requests a **new** token before the batch call.
        """
        self.get_bearer_token(force_new=True)

        payloads = []
        for opt in options:
            payloads.append(
                opt.to_update_payload(
                    option_set_name,
                    language_code,
                    merge_labels,
                    entity_logical_name=entity_logical_name,
                    attribute_logical_name=attribute_logical_name,
                )
            )

        boundary = f"batch_{int(time.time() * 1000)}"
        body = self._build_batch_body("UpdateOptionValue", payloads, boundary)

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": f"multipart/mixed;boundary={boundary}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        if continue_on_error:
            headers["Prefer"] = "odata.continue-on-error"

        if progress_callback:
            progress_callback(f"Sending batch UPDATE for {len(options)} options …")

        resp = requests.post(
            f"{self._base_url}/$batch",
            headers=headers,
            data=body.encode("utf-8"),
            timeout=300,
        )
        try:
            resp.raise_for_status()
        except Exception:
            print("Batch request body:\n", body)
            print("Batch response:\n", resp.text)
            raise

        report = self._parse_batch_response(resp.text, options)
        if progress_callback:
            progress_callback(
                f"Batch UPDATE complete: {report.succeeded}/{report.total} succeeded"
            )
        return report

    def bulk_delete_options(
        self,
        options: list[OptionItem],
        option_set_name: str,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
        continue_on_error: bool = True,
        progress_callback: Any = None,
    ) -> BatchReport:
        """
        $batch DeleteOptionValue for many options at once.
        Always requests a **new** token before the batch call.
        ``continue_on_error`` defaults to True for deletes (some values may
        already be missing).
        """
        self.get_bearer_token(force_new=True)

        payloads = []
        for opt in options:
            payloads.append(
                opt.to_delete_payload(
                    option_set_name,
                    entity_logical_name=entity_logical_name,
                    attribute_logical_name=attribute_logical_name,
                )
            )

        boundary = f"batch_{int(time.time() * 1000)}"
        body = self._build_batch_body("DeleteOptionValue", payloads, boundary)

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": f"multipart/mixed;boundary={boundary}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        if continue_on_error:
            headers["Prefer"] = "odata.continue-on-error"

        if progress_callback:
            progress_callback(f"Sending batch DELETE for {len(options)} options …")

        resp = requests.post(
            f"{self._base_url}/$batch",
            headers=headers,
            data=body.encode("utf-8"),
            timeout=300,
        )
        try:
            resp.raise_for_status()
        except Exception:
            print("Batch request body:\n", body)
            print("Batch response:\n", resp.text)
            raise

        report = self._parse_batch_response(resp.text, options)
        if progress_callback:
            progress_callback(
                f"Batch DELETE complete: {report.succeeded}/{report.total} succeeded"
            )
        return report

    # ------------------------------------------------------------------
    # Duplicate-safe insert
    # ------------------------------------------------------------------
    def safe_bulk_insert(
        self,
        options: list[OptionItem],
        option_set_name: str,
        language_code: int = 1033,
        *,
        entity_logical_name: str | None = None,
        attribute_logical_name: str | None = None,
        continue_on_error: bool = False,
        progress_callback: Any = None,
    ) -> tuple[BatchReport | None, list[OptionItem]]:
        """
        Insert only options whose *Value* does not already exist.
        Returns ``(report, skipped)`` where ``skipped`` lists duplicates.
        """
        existing = self.get_existing_values(
            option_set_name,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
        )
        to_insert = [o for o in options if o.value not in existing]
        skipped = [o for o in options if o.value in existing]

        if progress_callback and skipped:
            progress_callback(
                f"Skipping {len(skipped)} duplicate(s) already in the OptionSet"
            )

        if not to_insert:
            if progress_callback:
                progress_callback("Nothing to insert – all options already exist.")
            return None, skipped

        report = self.bulk_insert_options(
            to_insert,
            option_set_name,
            language_code,
            entity_logical_name=entity_logical_name,
            attribute_logical_name=attribute_logical_name,
            continue_on_error=continue_on_error,
            progress_callback=progress_callback,
        )
        return report, skipped


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------
def create_service_from_env(env_path: str = ".env") -> DataverseOptionSetService:
    """Instantiate the service using values from a .env file."""
    import os

    load_dotenv(env_path)
    return DataverseOptionSetService(
        environment_url=os.environ["environmentUrl"],
        tenant_id=os.environ["tenant_id"],
        client_id=os.environ["client_id"],
        client_secret=os.environ["client_secret"],
    )

