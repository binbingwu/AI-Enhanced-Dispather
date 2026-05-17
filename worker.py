"""
Redis Queue worker for dispatcher technician requests.

Run one worker for strict one-by-one processing:
    python worker.py

Run more worker processes later if the system needs more throughput.
"""

from __future__ import annotations

from rq import Worker

from dispatcher_queue import QueueConfig, get_dispatch_queue, get_redis_connection


def main() -> None:
    config = QueueConfig.from_env()
    connection = get_redis_connection(config)
    queue = get_dispatch_queue(config)
    worker = Worker([queue], connection=connection)

    print(f"Starting dispatcher worker for queue: {config.queue_name}")
    worker.work()


if __name__ == "__main__":
    main()

