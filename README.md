# GreenOps Cloud Pulse – Smart Fleet & Cold-Chain Telemetry Tracker

CST8922 – Capstone Project · Group 3 · Category 4: IoT & Real-Time Processing

Six simulated refrigerated trucks send GPS, temperature, humidity and door readings every 10 seconds. The system checks every
reading against the cargo's safe range, emails staff within 30 seconds when something goes wrong, keeps a raw archive for audits
and shows the fleet on a live map. This repository is the **Part 3 build**: the complete pipeline runs **on a local server** with
Docker stand-ins for each Azure service in the Part 2 design, and the same code is ready for Azure (`infra/terraform`).

![Architecture](docs/architecture-local.png)

## Who owns what

| Role | Owner | Folder | Requirements |
|---|---|---|---|
| 1 – Edge & Telemetry Simulation | Ying Song | `simulator/`, `contracts/` | FR-01, FR-02 |
| 2 – Cloud Ingestion & Message Broker | Marcelbriaud Wafotchoupe | `broker/`, `scripts/`, `infra/` | FR-03, FR-04 |
| 3 – Event Processing & Alerting | Shi Wang | `functions/shared/alert*.py`, `fleet_watcher.py`, `mail-relay/` | FR-05 – FR-08 |
| 4 – Cloud Storage & Cost Analysis | Durmusali Unal | `functions/shared/repository.py`, archive in `broker/router` | FR-09, F11 cost model |
| 5 – Dashboard & User Deliverables | Idowu Ayeni | `dashboard/`, `functions/shared/dashboard_api.py` | FR-10, FR-11 |

## Azure design → local stand-in

| Part 2 (Azure) | Local (this build) | Port |
|---|---|---|
| Truck simulator | `simulator` – Python 3.12, one process per truck, fault API | 8090 |
| Azure IoT Hub (X.509 per device, own topic) | `mosquitto` – MQTT with mutual TLS, CA + CRL, topic ACL | 8883 |
| IoT Hub message routing | `router` – to the Alert Function (batches, retries, dead-letter) and the archive | – |
| Azure Functions (alerts, fleet watcher, Fleet API) | `functions` – the official Azure Functions Python image | 7071 |
| Azure Logic App (email) | `mail-relay` → `mailpit` inbox | 8025 |
| Azure Cosmos DB | `cosmos` – Cosmos DB emulator (Data Explorer on 1234) | 8081 |
| Azure Blob Storage | `azurite` | 10000 |
| Azure Static Web Apps | `dashboard` – nginx serving the React build | **5173** |

## Run it

```bash
python3 scripts/init_local.py       # create local operator/service credentials
bash scripts/make_certs.sh          # 1. create the device certificates (never committed)
docker compose up -d --build        # 2. start all 10 services
# 3. open http://localhost:5173 (dashboard) and http://localhost:8025 (alert inbox)
docker compose down                 # stop
```

Connect an operator key from `.env` in the dashboard, then open **System & demo**.
Direct simulator control requires `Authorization: Bearer <SIM_CONTROL_TOKEN>`. For example:
`curl -X POST localhost:8090/trucks/TRK-003/fault -H 'Authorization: Bearer <SIM_CONTROL_TOKEN>' -H 'Content-Type: application/json' -d '{"scenario":"compressor"}'`

## Run it on Azure

The same code runs on the Azure services from the Part 2 design. The six trucks stay on a PC (they are the "edge"),
and everything else is in Azure.

```bash
# 1. Infrastructure (Terraform, azurerm) – settings go in infra/terraform/azure.auto.tfvars (not committed),
#    including operator_tokens = { "<random key, 32+ chars>" = "<operator name>" } and a random
#    delivery_callback_token (32+ chars); with no operator_tokens the dashboard is read-only.
cd infra/terraform && terraform init && terraform plan -out=tfplan   # review the plan, then:
terraform apply tfplan && cd ../..
# 2. Register each truck's certificate in IoT Hub (Role 2)
bash scripts/register_azure_devices.sh "$(terraform -chdir=infra/terraform output -raw iot_hub_name)"
# 3. Publish the Functions and the dashboard
bash scripts/deploy_azure_app.sh
# 4. Start the trucks on this PC (they send to IoT Hub and read dashboard faults from the Fleet API)
bash scripts/start_azure_trucks.sh          # stop: docker compose -f docker-compose.azure.yml down
```

| Local stand-in | Azure (deployed) |
|---|---|
| Mosquitto + router | IoT Hub B1 (X.509 thumbprint per truck) + message routes to the Alert Function and Blob archive |
| Functions container (HTTP trigger) | Function app, Flex Consumption, IoT Hub trigger, managed identity for Cosmos DB |
| mail-relay + Mailpit | Logic App → Azure Communication Services email |
| Cosmos DB emulator | Cosmos DB for NoSQL (free tier, or serverless when the free-tier slot is taken) |
| Azurite | Storage account, `telemetry-archive` container, 30-day move to the Archive tier |
| nginx | Static Web Apps (Free) – calls the Function app directly (CORS) |
| simulator fault API | `/api/sim/trucks` on the Function app; the trucks poll it (`FAULTS_URL`) |

## Tests

| Suite | Command | Tests |
|---|---|---|
| Simulator | `cd simulator && python -m pytest` | 22 |
| Broker security (live broker) | `python -m pytest broker/tests` | 5 |
| Router | `cd broker/router && python -m pytest` | 11 |
| Functions + storage contract | `cd functions && python -m pytest` (`COSMOS_ENDPOINT=http://localhost:8081` adds Cosmos integration cases) | 51 / 71 |
| Mail relay | `cd mail-relay && python -m pytest` | 7 |
| Dashboard | `cd dashboard && npm test` | 17 |
| Browser regressions (dashboard in Chromium) | `cd dashboard && npm run build && npm run test:browser` | 6 scenarios, 15 views |
| **End to end** (whole system) | `docker compose -f docker-compose.yml -f e2e/compose.e2e.yml up -d --build && python -m pytest e2e` | 9 |

GitHub Actions (`.github/workflows/ci.yml`) runs every suite on each push and pull request.

## Message format

`contracts/telemetry.schema.json` (Part 1, Appendix A) – about 0.3 KB per message.

## Audit remediation and upgrades

See [the remediation and rollout notes](docs/audit-2026-10-07/FIXES.md) for authentication, persistence, coordinated API upgrades and test instructions. The audit findings and UI recommendations are preserved alongside that document.
