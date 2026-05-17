"""
Slack API layer for the AI-Enhanced Dispatcher system.

This file is intentionally separate from api_connectors.py because Slack is the
main technician-facing request channel:
- Receive requests from technicians through Slack Events API or slash commands.
- Put the request into Redis Queue immediately.
- Let background workers route the request to SharePoint, Excel Online, Google
  Maps, Oracle, or the local AI model.
- Let workers reply to the technician in Slack with the final result.

Keys and secrets are loaded from environment variables. Do not hard-code Slack
tokens or signing secrets in this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from slack_sdk.signature import SignatureVerifier

from api_connectors import ConnectorConfigError, required_env
from dispatcher_queue import enqueue_technician_request


load_dotenv()


@dataclass(frozen=True)
class SlackConfig:
    bot_token: str
    signing_secret: str
    default_channel_id: str
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "SlackConfig":
        return cls(
            bot_token=required_env("SLACK_BOT_TOKEN"),
            signing_secret=required_env("SLACK_SIGNING_SECRET"),
            default_channel_id=os.getenv("SLACK_DEFAULT_CHANNEL_ID", "").strip(),
            host=os.getenv("SLACK_API_HOST", "0.0.0.0").strip(),
            port=int(os.getenv("SLACK_API_PORT", "8080")),
        )


def create_app() -> Flask:
    config = SlackConfig.from_env()
    app = Flask(__name__)
    verifier = SignatureVerifier(signing_secret=config.signing_secret)

    @app.before_request
    def verify_slack_signature() -> tuple[Any, int] | None:
        if not request.path.startswith("/slack/"):
            return None

        is_valid = verifier.is_valid_request(
            body=request.get_data(),
            headers=dict(request.headers),
        )
        if not is_valid:
            return jsonify({"error": "invalid Slack signature"}), 403

        return None

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.post("/slack/events")
    def slack_events() -> tuple[Any, int]:
        payload = request.get_json(silent=True) or {}

        if payload.get("type") == "url_verification":
            return jsonify({"challenge": payload.get("challenge", "")}), 200

        event = payload.get("event", {})
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return jsonify({"status": "ignored"}), 200

        text = event.get("text", "")
        channel_id = event.get("channel") or config.default_channel_id
        user_id = event.get("user")
        thread_ts = event.get("thread_ts") or event.get("ts")
        request_id = payload.get("event_id")

        if channel_id and text:
            job_id = enqueue_technician_request(
                text=text,
                channel_id=channel_id,
                user_id=user_id,
                thread_ts=thread_ts,
                source="slack_event",
                request_id=request_id,
            )
            return jsonify({"status": "queued", "job_id": job_id}), 200

        return jsonify({"status": "ok"}), 200

    @app.post("/slack/commands/dispatch")
    def slack_dispatch_command() -> tuple[Any, int]:
        text = request.form.get("text", "")
        user_id = request.form.get("user_id")
        channel_id = request.form.get("channel_id") or config.default_channel_id
        request_id = request.form.get("trigger_id")

        if not channel_id:
            return jsonify(
                {
                    "response_type": "ephemeral",
                    "text": "Dispatcher request could not be queued: missing Slack channel.",
                }
            ), 200

        job_id = enqueue_technician_request(
            text=text,
            channel_id=channel_id,
            user_id=user_id,
            source="slack_command",
            request_id=request_id,
        )
        return jsonify(
            {
                "response_type": "ephemeral",
                "text": f"Request queued. Dispatcher job: {job_id}",
            }
        ), 200

    return app


def main() -> None:
    try:
        config = SlackConfig.from_env()
    except ConnectorConfigError as error:
        print(f"Slack configuration is incomplete: {error}")
        print("Copy .env.example to .env and fill in the Slack values.")
        return

    app = create_app()
    app.run(host=config.host, port=config.port)


if __name__ == "__main__":
    main()
