"""
Redis Queue integration for Slack technician requests.

Slack webhooks should acknowledge quickly. Heavy work such as local AI parsing,
SharePoint/Excel/Oracle updates, Google Maps lookup, and Slack final replies is
handled by RQ workers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from redis import Redis
from rq import Queue
from slack_sdk import WebClient

from api_connectors import required_env
from dispatcher_service import SlackDispatcherService


load_dotenv()


@dataclass(frozen=True)
class QueueConfig:
    redis_url: str
    queue_name: str
    default_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "QueueConfig":
        return cls(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
            queue_name=os.getenv("DISPATCH_QUEUE_NAME", "dispatcher_requests").strip(),
            default_timeout_seconds=int(os.getenv("DISPATCH_JOB_TIMEOUT_SECONDS", "300")),
        )


def get_redis_connection(config: QueueConfig | None = None) -> Redis:
    active_config = config or QueueConfig.from_env()
    return Redis.from_url(active_config.redis_url)


def get_dispatch_queue(config: QueueConfig | None = None) -> Queue:
    active_config = config or QueueConfig.from_env()
    return Queue(
        name=active_config.queue_name,
        connection=get_redis_connection(active_config),
        default_timeout=active_config.default_timeout_seconds,
    )


def enqueue_technician_request(
    *,
    text: str,
    channel_id: str,
    user_id: str | None = None,
    thread_ts: str | None = None,
    source: str = "slack",
    request_id: str | None = None,
) -> str:
    queue = get_dispatch_queue()
    job = queue.enqueue(
        process_technician_request,
        kwargs={
            "text": text,
            "channel_id": channel_id,
            "user_id": user_id,
            "thread_ts": thread_ts,
            "source": source,
            "request_id": request_id,
        },
    )
    return job.id


def process_technician_request(
    *,
    text: str,
    channel_id: str,
    user_id: str | None = None,
    thread_ts: str | None = None,
    source: str = "slack",
    request_id: str | None = None,
) -> dict[str, Any]:
    slack_client = WebClient(token=required_env("SLACK_BOT_TOKEN"))
    dispatcher = SlackDispatcherService(slack_client=slack_client)

    reply = dispatcher.handle_text_request(text=text, user_id=user_id)
    dispatcher.post_message(channel_id=channel_id, text=reply, thread_ts=thread_ts)

    return {
        "status": "completed",
        "source": source,
        "request_id": request_id,
        "channel_id": channel_id,
        "user_id": user_id,
    }

