# AI-Enhanced Dispatcher

This repository contains the first design step for an AI-enhanced dispatcher system.

The initial goal is to build a reusable API connector layer that can pull real-time or near-real-time operational data from:

- SharePoint Lists
- Excel Online files stored in Personal OneDrive
- Google Maps APIs
- Oracle Server
- Slack API
- Redis Queue

API keys, client secrets, tenant IDs, and database credentials are intentionally left blank. Fill them in through environment variables or a local `.env` file.

Slack is designed as a separate request intake layer. Technicians can send requests through Slack, the Slack API layer queues the request in Redis Queue, and a background worker processes each request by calling the AI model and the data connectors. The worker replies back to Slack after the task is complete.

## Project Structure

```text
.
|-- api_connectors.py    # Connector collection for external data sources
|-- dispatcher_queue.py  # Redis Queue setup and job functions
|-- dispatcher_service.py # Dispatcher request routing and Slack replies
|-- slack_api.py         # Slack request intake and queueing layer
|-- worker.py            # Background worker for queued technician requests
|-- .env.example         # Empty configuration template
|-- requirements.txt     # Python dependencies
`-- README.md
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env` and add the required credentials.

## Run

```powershell
python api_connectors.py
```

The script is currently a safe connector scaffold. It validates configuration and provides reusable methods for pulling data, but it does not include private keys or production-specific business logic.

## Run Slack API

```powershell
python slack_api.py
```

Expected Slack configuration:

- Event Request URL: `https://your-domain.com/slack/events`
- Slash Command Request URL: `https://your-domain.com/slack/commands/dispatch`

The Slack layer currently includes safe routing placeholders for technician requests. Production-specific command handling should be added in `SlackDispatcherService.handle_text_request`.

## Run Redis Queue Worker

Start Redis first, then run one worker:

```powershell
python worker.py
```

With one worker process, technician requests are handled one by one. To increase throughput later, start more worker processes or add separate queues for high-priority dispatch tasks.

## Request Flow

```text
Slack technician request
  -> slack_api.py validates Slack signature
  -> dispatcher_queue.py enqueues the request in Redis
  -> worker.py processes queued jobs one by one
  -> dispatcher_service.py calls AI/data connectors
  -> worker posts the final reply back to Slack
```
