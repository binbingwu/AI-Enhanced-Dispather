"""
Dispatcher request handling logic.

This service is called by background workers after Slack requests have been
accepted into Redis Queue.
"""

from __future__ import annotations

from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from api_connectors import ConnectorConfigError, build_connectors


class SlackDispatcherService:
    """Route technician Slack requests to dispatcher data connectors."""

    def __init__(self, slack_client: WebClient):
        self.slack_client = slack_client

    def handle_text_request(self, text: str, user_id: str | None = None) -> str:
        normalized = text.strip().lower()
        if not normalized:
            return "Please send a dispatcher request, for example: status, route, or sync."

        if normalized in {"help", "commands"}:
            return (
                "Available dispatcher commands: status, sync sharepoint, "
                "sync excel, route, oracle status."
            )

        if normalized == "status":
            return self._connector_status()

        if normalized == "sync sharepoint":
            return self._pull_sharepoint_summary()

        if normalized == "sync excel":
            return self._pull_excel_summary()

        if normalized.startswith("route "):
            return self._route_summary(text)

        if normalized == "oracle status":
            return self._oracle_status()

        user_label = f"<@{user_id}> " if user_id else ""
        return (
            f"{user_label}I received the request, but no dispatcher route is "
            "configured for it yet. Add the mapping in SlackDispatcherService."
        )

    def post_message(self, channel_id: str, text: str, thread_ts: str | None = None) -> None:
        payload: dict[str, Any] = {"channel": channel_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            self.slack_client.chat_postMessage(**payload)
        except SlackApiError as error:
            raise RuntimeError(f"Failed to post Slack message: {error.response}") from error

    def _connector_status(self) -> str:
        try:
            connectors = build_connectors()
        except ConnectorConfigError as error:
            return f"Connector configuration is incomplete: {error}"

        names = ", ".join(connectors.keys())
        return f"Dispatcher connector layer is available. Connectors: {names}."

    def _pull_sharepoint_summary(self) -> str:
        try:
            connector = build_connectors()["sharepoint"]
            items = connector.pull_items()
        except Exception as error:
            return f"SharePoint sync failed: {error}"

        return f"SharePoint sync completed. Pulled {len(items)} list items."

    def _pull_excel_summary(self) -> str:
        try:
            connector = build_connectors()["excel_online"]
            rows = connector.pull_table_rows()
        except Exception as error:
            return f"Excel Online sync failed: {error}"

        return f"Excel Online sync completed. Pulled {len(rows)} table rows."

    def _route_summary(self, text: str) -> str:
        try:
            route_text = text.split(" ", 1)[1]
            origin, destination = [part.strip() for part in route_text.split(" to ", 1)]
        except ValueError:
            return "Route format: route <origin> to <destination>"

        try:
            connector = build_connectors()["google_maps"]
            data = connector.directions(origin=origin, destination=destination)
        except Exception as error:
            return f"Google Maps route lookup failed: {error}"

        routes = data.get("routes", [])
        if not routes:
            return "No route was found."

        leg = routes[0].get("legs", [{}])[0]
        distance = leg.get("distance", {}).get("text", "unknown distance")
        duration = leg.get("duration", {}).get("text", "unknown duration")
        return f"Route found: {origin} to {destination}. Distance: {distance}. ETA: {duration}."

    def _oracle_status(self) -> str:
        try:
            build_connectors()["oracle"]
        except ConnectorConfigError as error:
            return f"Oracle configuration is incomplete: {error}"
        except Exception as error:
            return f"Oracle connector initialization failed: {error}"

        return "Oracle connector is configured. Add a safe named query before pulling records."

