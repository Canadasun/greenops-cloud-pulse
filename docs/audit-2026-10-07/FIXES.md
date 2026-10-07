# Audit remediation — 7 October 2026

The 20 findings in REPORT.md now have code/configuration fixes. The report remains the original audit record. This file describes the resulting behavior and operational requirements.

| Findings | Change |
|---|---|
| 1 | Server-owned operator identity mapped from secret bearer keys; all operator writes fail closed. Separate router, relay and workflow credentials. Browser keys stay in memory; no false login label. |
| 2, 3, 8 | Cosmos transactions serialize a truck's watermark, state and incident changes in one partition with ETag conflict retries. Late samples remain in history but cannot change current state. Replayed telemetry cannot overwrite original readings. In-memory transactions copy records and use the same isolation boundary. |
| 4 | Alert documents carry a durable notification outbox, attempt count, lease and exponential backoff. Fleet watcher retries even after resolution. Local relay persists send receipts keyed by alert ID. |
| 5, 7 | Per-event shape, size, timestamp, numeric and registered-identity validation; bad events are quarantined. Safe ranges always come from server cargo profiles. MQTT arrays no longer escape the callback. |
| 6 | Router SQLite spool survives restarts and storage failures; MQTT acknowledgement follows durable receipt. Archive and dead-letter failure retain data. Broker has a persistent session/store. A replay CLI is included. |
| 9 | Only genuine not-found reads produce empty records; storage failures propagate. |
| 10 | Trip changes and non-overdue journeys close stale delay incidents. Never-reporting trucks also alert after a persisted startup grace period. |
| 11 | API rejects invalid finite ranges, limits, status filters, cursors, IDs and control payloads with client errors. |
| 12–14 | Query identity clears unrelated chart data immediately; one in-flight poll per query; obsolete requests abort; requests time out. Every panel exposes error/stale/loading state and explicit retry. |
| 15 | All open incidents use a separate query; resolved history has stable keyset pagination and truck filters. Cosmos orders/limits server-side with a composite index. Health uses server aggregates instead of fetching all alert documents. |
| 16 | Mutation responses update displayed state immediately and trigger refresh. Per-item pending and success/failure feedback prevent accidental repeats. |
| 17 | Responsive incident cards, stacked mobile controls and contained tables; browser checks cover 320/390/768px across five views. |
| 18 | Azure lifecycle prefix includes the hub name used by the archive writer. |
| 19 | Trigger acceptance is shown as queued. The Logic App reports the actual email action result through an authenticated callback. A persisted workflow claim prevents separate retried trigger invocations from starting another send; callbacks from superseded attempts are ignored. |
| 20 | Fault choices use independent documents per truck, preserving concurrent edits. Legacy fault/state documents remain readable. |

The UI also adds a searchable fleet list, status filters including waiting trucks, URL-based truck/filter/view selection, active incidents before history, map fit/locate controls, timezone/date timestamps, chart pointer/keyboard inspection, a data table, selectable windows, outage gaps, accessible focus styles and higher-contrast badges. Demo controls and system health are secondary views. Accelerated simulator time is explicit and reported physical speed remains within its cap.

## Local setup and upgrade

1. Run `python3 scripts/init_local.py`. It appends missing random credentials to the ignored `.env` without overwriting existing settings, and sets mode 0600. Use one key from the `OPERATOR_TOKENS` object in the dashboard's operator connection form. Do not paste it into source files or a Vite environment variable.
2. For existing certificates, run `python3 scripts/stage_certs.py`. For a fresh checkout, run `bash scripts/make_certs.sh`; it now refuses to replace an existing CA. Runtime certificate folders contain only service identities, never the CA private key. The container images use UID 1000 for these local mounts.
3. Back up existing emulator/Azurite data before recreating an older stack: the old Compose file had no declared persistence. New named volumes protect data on subsequent recreates. Do not use `docker compose down -v` for data you want to retain.
4. Rebuild together using `docker compose up -d --build`. Dashboard and API must upgrade together because `/api/alerts` now returns `{items, next_cursor}`. The local Cosmos key path adds the composite index to existing alert containers. Existing truck state migrates on its next transaction; historical alerts and fault choices remain readable.
5. Local direct simulator writes require the separate `SIM_CONTROL_TOKEN`; the dashboard uses the central authenticated Functions fault API, which the simulator polls.

`broker/router/replay.py` accepts a downloaded dead-letter JSONL file and an ingestion URL, using `INGESTION_TOKEN`. It retains the source file. Replays store missing history but intentionally do not rewind a newer truck's live incident state.

## Azure rollout

Provision `operator_tokens` (secret key -> operator name) and a separate `delivery_callback_token` of at least 32 characters in ignored Terraform variables. Terraform updates the Cosmos index and creates workflow claim/result actions. Apply infrastructure before publishing the matching Functions/dashboard code; pause ingestion or schedule a maintenance window across the coordinated API change. Empty operator mappings leave all writes disabled.

The default IoT Hub plan is B1 to cover the six-truck simulation. The dashboard displays the configured SKU, allowance and base-cost assumption, explicitly excluding other services and usage; it is not an Azure bill forecast. Existing deployments must choose their own plan/cost values. The archive lifecycle correction applies to the configured blob prefix.

Registration now updates the primary device thumbprint while retaining the secondary for rotation. Certificate generation no longer silently regenerates the CA. Operator bearer keys are a deliberately small authentication mechanism for this app; named keys can be revoked individually by removing their mapping. An enterprise identity provider can replace this boundary without changing the write handlers' server-owned identity requirement.

## Delivery semantics and limits

“Sent” means the SMTP server or email action accepted/completed the send, not proof that a human received the message. HTTP 202 alone never sets that field. Logic App claim and callback retries handle duplicated triggers and delayed results. An accepted workflow with no callback remains visibly queued and must be investigated in Azure rather than falsely reported sent.

The router spool and local notification receipt database require their named volumes. Like any SMTP client without a transactional mail provider, a process crash precisely after SMTP acceptance but before receipt commit is an ambiguous delivery window; the deterministic Message-ID supports investigation, but this implementation does not claim exactly-once mailbox delivery. A storage outage that prevents durable receipt leaves MQTT unacknowledged and restarts the router.

Azure resources were not deployed during remediation. Validation and local integration results are recorded separately. The pre-existing running fleet was not replaced; a separate Docker project was used for end-to-end validation.

## Verification results

- Full Functions suite with Cosmos enabled: **71 passed**. The standalone memory run passed 51 tests and skipped the Cosmos-only test.
- Repository + reliability suite against the real local Cosmos emulator: **43 passed** (includes memory cases, concurrency, immutable replays, pagination, health aggregates and workflow claims).
- Simulator: **22 passed**.
- Router: **11 passed**, including retained archive/dead-letter data and restart recovery.
- MQTT security against isolated broker: **5 passed**.
- Mail relay: **7 passed**, including persistent duplicate suppression, retry and credential checks.
- Dashboard: **16 passed**; production build passed.
- Browser regression suite: operator access, acknowledge/fault feedback, truck-history identity, partial outages, history pagination, and all five views at **320/390/768px** passed.
- Full isolated Docker end-to-end suite: **9 passed in 248 seconds**.
- Terraform validation, Compose validation, Python compilation and `git diff --check` passed.

**Total across the full Functions, simulator, router, broker security, mail relay, dashboard unit and Docker E2E suites: 141 passing tests**, plus the browser regression scenarios.

Updated screenshots: [desktop](fixed/desktop.png), [mobile](fixed/mobile.png).

The separate preview/test stack is at **http://localhost:5273**, with its API on 7171. It uses accelerated test timings and separate volumes. The existing app on 5173 was not replaced. To stop the preview without deleting its data:

```bash
docker compose -p greenops-fix-tests -f docker-compose.yml -f e2e/compose.e2e.yml -f e2e/compose.isolated.yml stop
```

To reproduce browser checks after building the dashboard:

```bash
cd dashboard
npm ci
npx playwright install chromium
npm run build
npm run test:browser
```

The browser suite uses `functions/.venv/bin/python` by default. Override `GREENOPS_PYTHON` for another interpreter with `functions/requirements-dev.txt` installed. Browser tests run a temporary in-memory API and never touch the live fleet.
