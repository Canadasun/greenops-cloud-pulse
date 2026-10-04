# Azure Functions app

| Function | Trigger | Owner | Does |
|---|---|---|---|
| `alert_function` | HTTP `POST /api/telemetry` locally · IoT Hub trigger on Azure (`TRIGGER_MODE=iothub`) | Shi Wang (Role 3) | stores each reading, checks cargo limits and door time, raises / updates / resolves alerts, emails once per problem |
| `fleet_watcher` | Timer, every minute | Shi Wang (Role 3) | OFFLINE after 5 min without data, DELAYED after the ETA |
| `get_trucks`, `get_routes`, `get_history`, `get_alerts`, `ack_alert`, `get_health` | HTTP `GET/POST /api/...` | Idowu Ayeni (Role 5) | read-only Fleet API for the dashboard + acknowledge |

`shared/repository.py` (Durmusali Unal, Role 4) is the only code that talks to Cosmos DB: containers `telemetry`
(partition `/truck_id`, 7-day TTL), `alerts` (`/truck_id`) and `reference` (`/doc_type`).

Tests: `python -m pytest` – 32 tests (alert rules = Part 1 acceptance criteria, Fleet API, function registration, storage contract).
With the Cosmos DB emulator running, `COSMOS_ENDPOINT=http://localhost:8081 python -m pytest` also runs the storage contract against Cosmos (39 tests).
