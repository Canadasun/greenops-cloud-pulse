# Azure Functions app

| Function | Trigger | Owner | Does |
|---|---|---|---|
| `alert_function` | HTTP `POST /api/telemetry` locally · IoT Hub trigger on Azure (`TRIGGER_MODE=iothub`) | Shi Wang (Role 3) | stores each batch of readings with **one transaction per truck**, checks cargo limits and door time, raises / updates / resolves alerts, emails once per problem and texts cargo emergencies (SMS) |
| `fleet_watcher` | Timer, every minute | Shi Wang (Role 3) | reads the whole fleet in **one snapshot query**, decides on that copy and only opens a transaction for a truck that changes: OFFLINE after 5 min without data, DELAYED after the ETA; retries unsent emails and texts |
| `get_trucks`, `get_routes`, `get_history`, `get_alerts`, `get_health` | HTTP `GET` | Idowu Ayeni (Role 5) | Fleet API for the dashboard – any signed-in account |
| `ack_alert`, `set_fault`, `clear_fault` | HTTP `POST/DELETE` | Idowu Ayeni (Role 5) | acknowledge an alert, set a demo fault – operators only (`OPERATOR_EMAILS`) |
| `get_session` | HTTP `GET /api/session` | Idowu Ayeni (Role 5) | who is signed in and whether they may act |
| `get_faults` | HTTP `GET /api/sim/trucks` | Ying Song (Role 1) | faults for the trucks (signed-in user or the trucks' own token) |
| `claim_dispatch`, `delivery_result` | HTTP `POST /api/alerts/{id}/dispatch`, `/delivery` | Shi Wang (Role 3) | email Logic App callbacks: one workflow per alert, then the result |

Sign-in (F12, Part 4): `shared/session.py` verifies the 15-minute HS256 session that `swa-api` issues after the Microsoft sign-in
(`SESSION_SIGNING_KEY`, made by Terraform); `shared/auth.py` decides view or act. There are no operator keys any more.
SMS (F13, Part 4): `shared/notifier.py` `SmsNotifier` posts a 160-character plain-text message to `SMS_URL`; with no `SMS_URL` the
channel is off and no alert gets an `sms_status`.

`shared/repository.py` (Durmusali Unal, Role 4) is the only code that talks to Cosmos DB: containers `telemetry`
(partition `/truck_id`, 7-day TTL), `alerts` (`/truck_id`) and `reference` (`/doc_type`).

Tests: `python -m pytest` – 104 tests (alert rules = Part 1 acceptance criteria, Fleet API, function registration, storage
contract, reliability of email delivery, sign-in, SMS, and `test_efficiency.py`, which counts database requests so the 100-truck
optimisations cannot quietly regress). With the Cosmos DB emulator running, `COSMOS_ENDPOINT=http://localhost:8081 python -m pytest`
also runs the storage contract against Cosmos (143 tests).
