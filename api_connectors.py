"""
API connector collection for the AI-Enhanced Dispatcher system.

Design step 1:
- Connect to SharePoint Lists through Microsoft Graph.
- Connect to Excel Online files stored in Personal OneDrive through Microsoft Graph.
- Connect to Google Maps APIs.
- Connect to Oracle Server.

Credentials are intentionally loaded from environment variables and left blank in
.env.example. Do not hard-code keys or secrets in this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import oracledb
import requests
from dotenv import load_dotenv


load_dotenv()


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GOOGLE_MAPS_BASE_URL = "https://maps.googleapis.com/maps/api"


class ConnectorConfigError(RuntimeError):
    """Raised when a connector is missing required configuration."""


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConnectorConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class MicrosoftGraphConfig:
    tenant_id: str
    client_id: str
    client_secret: str

    @classmethod
    def from_env(cls) -> "MicrosoftGraphConfig":
        return cls(
            tenant_id=required_env("MS_TENANT_ID"),
            client_id=required_env("MS_CLIENT_ID"),
            client_secret=required_env("MS_CLIENT_SECRET"),
        )


class MicrosoftGraphClient:
    """Small Microsoft Graph client used by SharePoint and Excel connectors."""

    def __init__(self, config: MicrosoftGraphConfig):
        self.config = config
        self._access_token: str | None = None

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        token_url = (
            f"https://login.microsoftonline.com/{self.config.tenant_id}"
            "/oauth2/v2.0/token"
        )
        response = requests.post(
            token_url,
            data={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = self.get_access_token()
        response = requests.request(
            method=method,
            url=f"{GRAPH_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                **kwargs.pop("headers", {}),
            },
            timeout=kwargs.pop("timeout", 30),
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else {}


@dataclass(frozen=True)
class SharePointListConfig:
    hostname: str
    site_path: str
    list_id: str

    @classmethod
    def from_env(cls) -> "SharePointListConfig":
        return cls(
            hostname=required_env("SHAREPOINT_HOSTNAME"),
            site_path=required_env("SHAREPOINT_SITE_PATH"),
            list_id=required_env("SHAREPOINT_LIST_ID"),
        )


class SharePointListConnector:
    """Pull list items from SharePoint using Microsoft Graph."""

    def __init__(self, graph: MicrosoftGraphClient, config: SharePointListConfig):
        self.graph = graph
        self.config = config

    def get_site_id(self) -> str:
        site = self.graph.request(
            "GET",
            f"/sites/{self.config.hostname}:/{self.config.site_path}",
        )
        return site["id"]

    def pull_items(self, expand_fields: bool = True) -> list[dict[str, Any]]:
        site_id = self.get_site_id()
        expand = "?expand=fields" if expand_fields else ""
        data = self.graph.request(
            "GET",
            f"/sites/{site_id}/lists/{self.config.list_id}/items{expand}",
        )
        return data.get("value", [])


@dataclass(frozen=True)
class ExcelOnlineConfig:
    user_id: str
    drive_id: str
    workbook_item_id: str
    worksheet_name: str
    table_name: str

    @classmethod
    def from_env(cls) -> "ExcelOnlineConfig":
        return cls(
            user_id=required_env("ONEDRIVE_USER_ID"),
            drive_id=required_env("ONEDRIVE_DRIVE_ID"),
            workbook_item_id=required_env("ONEDRIVE_WORKBOOK_ITEM_ID"),
            worksheet_name=required_env("EXCEL_WORKSHEET_NAME"),
            table_name=required_env("EXCEL_TABLE_NAME"),
        )


class ExcelOnlineConnector:
    """Pull workbook table rows from Excel Online in Personal OneDrive."""

    def __init__(self, graph: MicrosoftGraphClient, config: ExcelOnlineConfig):
        self.graph = graph
        self.config = config

    def pull_table_rows(self) -> list[dict[str, Any]]:
        path = (
            f"/users/{self.config.user_id}/drives/{self.config.drive_id}"
            f"/items/{self.config.workbook_item_id}"
            f"/workbook/worksheets/{self.config.worksheet_name}"
            f"/tables/{self.config.table_name}/rows"
        )
        data = self.graph.request("GET", path)
        return data.get("value", [])


@dataclass(frozen=True)
class GoogleMapsConfig:
    api_key: str

    @classmethod
    def from_env(cls) -> "GoogleMapsConfig":
        return cls(api_key=required_env("GOOGLE_MAPS_API_KEY"))


class GoogleMapsConnector:
    """Pull map, distance, geocoding, and routing data from Google Maps APIs."""

    def __init__(self, config: GoogleMapsConfig):
        self.config = config

    def geocode(self, address: str) -> dict[str, Any]:
        return self._get("/geocode/json", {"address": address})

    def distance_matrix(
        self,
        origins: list[str],
        destinations: list[str],
        mode: str = "driving",
    ) -> dict[str, Any]:
        return self._get(
            "/distancematrix/json",
            {
                "origins": "|".join(origins),
                "destinations": "|".join(destinations),
                "mode": mode,
            },
        )

    def directions(
        self,
        origin: str,
        destination: str,
        mode: str = "driving",
    ) -> dict[str, Any]:
        return self._get(
            "/directions/json",
            {
                "origin": origin,
                "destination": destination,
                "mode": mode,
            },
        )

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(
            f"{GOOGLE_MAPS_BASE_URL}{endpoint}",
            params={**params, "key": self.config.api_key},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()


@dataclass(frozen=True)
class OracleConfig:
    user: str
    password: str
    dsn: str

    @classmethod
    def from_env(cls) -> "OracleConfig":
        return cls(
            user=required_env("ORACLE_USER"),
            password=required_env("ORACLE_PASSWORD"),
            dsn=required_env("ORACLE_DSN"),
        )


class OracleServerConnector:
    """Pull operational records from Oracle Server."""

    def __init__(self, config: OracleConfig):
        self.config = config

    def fetch_rows(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with oracledb.connect(
            user=self.config.user,
            password=self.config.password,
            dsn=self.config.dsn,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, parameters or {})
                columns = [column[0].lower() for column in cursor.description]
                return [
                    dict(zip(columns, row, strict=True))
                    for row in cursor.fetchall()
                ]


def build_connectors() -> dict[str, Any]:
    graph = MicrosoftGraphClient(MicrosoftGraphConfig.from_env())
    return {
        "sharepoint": SharePointListConnector(
            graph=graph,
            config=SharePointListConfig.from_env(),
        ),
        "excel_online": ExcelOnlineConnector(
            graph=graph,
            config=ExcelOnlineConfig.from_env(),
        ),
        "google_maps": GoogleMapsConnector(GoogleMapsConfig.from_env()),
        "oracle": OracleServerConnector(OracleConfig.from_env()),
    }


def main() -> None:
    try:
        connectors = build_connectors()
    except ConnectorConfigError as error:
        print(f"Configuration is incomplete: {error}")
        print("Copy .env.example to .env and fill in the required values.")
        return

    print("Connector layer initialized.")
    print(f"Available connectors: {', '.join(connectors.keys())}")


if __name__ == "__main__":
    main()

