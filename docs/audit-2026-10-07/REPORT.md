# GreenOps Cloud Pulse audit — 7 October 2026

Audited the current working tree, including its pre-existing uncommitted Azure changes. Application source was not changed. Scope: React UI, API handlers, alert lifecycle, Cosmos repository, MQTT router, simulator, mail relay, contracts, Docker configuration, Terraform, deployment/certificate scripts, and tests.

The main risks are incorrect alert state after delayed/repeated delivery, missing notification recovery, unprotected control endpoints, and misleading dashboard states. Happy-path tests pass, but they do not cover these failure modes.

## Verification and limits

| Check | Result |
|---|---|
| Functions suite, memory repository | 35 passed; 1 Cosmos-only test skipped |
| Cosmos repository contract suite | 15 passed, including memory and real local emulator cases |
| Simulator | 21 passed |
| Router | 8 passed |
| Mail relay | 3 passed |
| Dashboard | 11 passed |
| Dashboard production build | Passed |
| Browser | Current production build, Chromium, 1440px desktop and 390px mobile; live local read endpoints plus mocked failures/data |
| Local API smoke check | Six reporting trucks; health and history returned HTTP 200 |
| Focused backend probes | Reproduced ordering, replay, notification recovery, invalid input, concurrency, archive failure, and swallowed database errors |

The simulator HTTP test initially failed because the sandbox prohibited binding a socket; it passed outside the sandbox. That was an environment restriction, not an app defect. Cosmos tests created isolated `test-*` databases in the emulator. Browser probes did not mutate fleet records.

The live backend is the existing container build; current backend source was separately checked through unit tests and direct calls. The full E2E suite was reviewed but not executed: it deletes the shared Mailpit inbox, changes fleet faults, and issues/revokes certificates. Broker publishing tests were not run against the shared fleet because they publish incomplete telemetry. No Azure deployment, destructive testing, dependency advisory scan, or cloud load test was performed. Findings based on cloud configuration are identified below; this report does not claim a bug-free system outside the exercised cases.

## High-priority findings

### 1. Control endpoints have no authenticated operator identity

**Evidence:** `functions/function_app.py:24,96,117,127`; `dashboard/src/App.jsx:12,37`; Terraform configures CORS but no authentication layer. All HTTP functions inherit `ANONYMOUS`. Acknowledgement accepts an arbitrary body `user`. Simulator fault controls also lack authentication.

**Impact:** Anyone able to reach the configured Function URL can acknowledge alerts as another user or change simulated truck faults. “Signed in: Dispatcher (demo)” is a hard-coded label, not a login. The local HTTP telemetry endpoint also bypasses the MQTT certificate boundary. This is especially important if the demo is internet-accessible.

**Fix:** Protect writes with verified identity and role checks, derive acknowledger identity server-side, isolate demo controls, and restrict local ingestion to the router. Keep the demo label explicit until real authentication exists.

### 2. Older telemetry can overwrite newer state and resolve a real breach

**Reproduced:** Process a 10°C reading at T+10, then a 4°C reading at T. Latest state moves backwards to T and the temperature alert becomes RESOLVED. `functions/shared/alerting.py:28–51` only sorts within each batch and unconditionally replaces state.

**Impact:** Dashboard location, temperatures, door timer, and alert status can regress after delayed delivery. Any arriving message also resolves OFFLINE, even if its timestamp is stale.

**Fix:** Normalize timestamps, enforce a per-truck monotonic processing watermark with concurrency protection, retain late samples in history without applying them to current state, and require fresh evidence before resolving OFFLINE.

### 3. Replayed batches create duplicate alerts and emails

**Reproduced:** Deliver a batch containing breach → recovery twice. Storage contains two readings, but the service creates two alerts and sends two emails. `functions/shared/alerting.py:30–50` deduplicates reading storage only; alert side effects repeat.

**Impact:** A lost HTTP response followed by router retry duplicates notifications. This also affects replay after partial batch failure.

**Fix:** Persist processing identity/watermarks and make alert transitions and notification enqueueing idempotent. Test replay after partial success and after a lost response.

### 4. A temporary email failure suppresses notification indefinitely

**Reproduced:** A notifier fails its first call and would succeed thereafter. Three ongoing breach readings produce exactly one send attempt and `email_sent_at=None`. `functions/shared/alert_service.py:19–36` returns early for existing alerts and never retries the failed notification.

**Fix:** Use a durable notification outbox with bounded backoff, attempt status, and idempotency. Retrying delivery should not depend on a new breach occurring.

### 5. Invalid telemetry can fail a whole batch or escape the MQTT callback

**Reproduced:** A valid reading plus a message missing `timestamp` raises `KeyError` before either is stored. Router input `[]` raises uncaught `AttributeError`. See `functions/shared/alerting.py:29`, `functions/function_app.py:51–63`, `broker/router/router.py:32–40`.

**Impact:** One malformed reading disrupts unrelated readings. An unknown route can also break fleet watching after it is stored. The JSON schema is tested against simulator output but is not enforced at ingress.

**Fix:** Validate shape, finite numeric values, timestamp/timezone, known truck/route/cargo relationships, and message size. Quarantine individual invalid events with a reason and continue valid events. Validate Azure event bodies individually rather than decoding the entire batch in a single list comprehension.

### 6. Archive upload failure loses buffered telemetry

**Reproduced:** Queue a message, make storage upload fail, call `flush_archive()`: the exception propagates and `archive_buffer` is empty. `broker/router/router.py:65–71`. Dead-letter upload has a similar unhandled failure at line 63; the main loop does not catch either.

**Impact:** Router restart cannot recover the drained in-memory data. Ordinary process restarts also lose pending buffers; the MQTT setup does not provide a durable application queue.

**Fix:** Persist a spool before acknowledging receipt, retain batches until successful archive/delivery, retry storage failures without terminating the processing loop, and provide dead-letter replay tooling.

### 7. A device can redefine its own safe temperature limits

**Reproduced:** A vaccine reading at 20°C with supplied limits -40 to 60 creates no alert. `functions/shared/alerting.py:17` trusts `temp_min_c`/`temp_max_c` from telemetry instead of the authoritative cargo profile. Cargo identity itself is not checked against fleet reference data.

**Fix:** Resolve the registered truck's cargo and limits on the server, reject inconsistent metadata, and preserve reported limits separately if needed for diagnostics.

### 8. Concurrent creation violates one-alert/one-email semantics

**Reproduced with a controlled interleaving:** Two calls both finish `find_open()` before either saves. Both create a distinct ACTIVE alert and send email. `functions/shared/alert_service.py:19–27`, `functions/shared/repository.py:121–133` use read-then-upsert without a uniqueness or compare-and-swap boundary.

**Impact:** Concurrent ingestion or watcher invocations can duplicate alerts. Unconditional writes also permit acknowledgement/resolution updates to overwrite one another; this latter race was identified by inspection, not exercised against Azure.

**Fix:** Use deterministic incident/open-state keys and transactional or conditional writes within the appropriate partition, with a durable outbox for notification side effects. Test actual Cosmos interleavings before enabling scale-out.

## Other confirmed defects and configuration issues

| # | Priority | Finding and evidence | Recommended correction |
|---|---|---|---|
| 9 | Medium | **Database failures are treated as missing records.** Injected connection errors return empty state/faults from `repository.py:147–163`. A transient failure can reset door duration or clear remote demo faults; later writes can overwrite real state. | Catch only a verified not-found response; propagate/retry availability and authorization failures. |
| 10 | Medium | **A DELAYED alert can remain active into the next trip.** Reproduced by replacing an overdue reading with a future ETA away from the destination. `fleet_watcher.py:25–31` resolves only when arrival is observed; the watcher can miss the simulator's short arrival interval. | Track trip identity and close the previous trip's incident; handle a new non-overdue journey explicitly. |
| 11 | Medium | **Invalid API input raises server exceptions.** Direct handler calls with `hours=abc`, `hours=NaN`, `limit=abc`, or fault body `[1]` raise ValueError/AttributeError. `function_app.py:87,93,123`, `dashboard_api.py:62,83`. | Validate finite bounded numeric parameters, JSON object shape and field types; return consistent 400 responses. |
| 12 | Medium | **Truck selection briefly displays another truck's chart.** Browser probe loaded 4°C/5°C for TRK-001, switched to frozen TRK-004 while delaying its history, and displayed two breach dots under TRK-004's -25 to -15°C range. `api.js:33–50`, `TruckDetail.jsx:7,27`. On a new request failure, wrong-truck data can persist. | Key history by truck ID; clear or correctly cache per identity, and use history's own limits. |
| 13 | Medium | **Polling responses can arrive out of order.** `api.js:39–48` starts a request every interval without an in-flight guard, timeout or response sequence check. Source-confirmed; not load-tested. | Schedule the next poll after completion or ignore superseded responses; abort on cleanup and enforce timeout/backoff. |
| 14 | Medium | **Partial API failures are hidden.** Browser-injected alerts HTTP 503 leaves “Loading alerts…” while the header says “Updated 0 s ago.” Only `trucks.error` is rendered in `App.jsx:37`; alert/health/history/route/fault fetch errors are ignored. Existing data also stays visible without a stale label. | Give each panel loading, empty, stale, failed and retry states, with its own last-success time. |
| 15 | Medium | **Older active incidents disappear from the action list.** `api.js:22` requests only the newest 50 alerts across all statuses; `AlertHistory.jsx` offers no paging/filtering. Fifty newer resolved alerts can hide a still-active incident that the user needs to acknowledge. | Fetch open incidents separately; paginate resolved history and add status/truck filters. |
| 16 | Medium | **Successful writes are not reflected immediately.** `App.jsx:49` calls `force()` but polling's empty dependency array does not refetch; `FaultPanel.jsx:18` stays controlled by the previous polled value. Source-confirmed. | Expose query invalidation/refetch or update local cached state from the response; retain per-row pending state until reconciliation. |
| 17 | Medium | **Mobile content extends outside the viewport.** Measured 534px document width on a 390px viewport with one active alert. The acknowledge button falls outside the card. `styles.css:43–54` lacks table containment and a narrow-screen fault layout. | Use mobile alert cards or a contained horizontally scrollable table; stack fault fields and verify keyboard/touch access at 320/390/768px. |
| 18 | Medium | **Azure archive lifecycle prefix does not match produced blobs.** `infra/terraform/main.tf:50` filters `telemetry-archive/telemetry/`, but line 68 creates `telemetry-archive/<hub>/telemetry/...`. Configuration-confirmed, not deployed in this audit. | Align the naming format and lifecycle filter and test a representative generated path. Azure matches container name plus blob prefix ([Microsoft documentation](https://learn.microsoft.com/en-us/azure/storage/blobs/lifecycle-management-policy-structure)). |
| 19 | Medium | **Azure email “sent” status records acceptance, not send outcome.** `notifier.py:22–25` accepts any successful HTTP response; `alert_service.py:37–39` marks sent. Terraform's Logic App has no Response action after email completion. Such workflows immediately return 202 ([Microsoft documentation](https://learn.microsoft.com/en-us/azure/connectors/connectors-native-reqres)). | Record queued/accepted separately from sent/failed and reconcile the workflow/provider result. Measure latency from telemetry/event time to a defined send milestone; current `email_seconds` measures only the HTTP call. |
| 20 | Medium | **Concurrent fault edits can overwrite each other.** `repository.py:165–166` reads and replaces the complete faults dictionary. Two operators editing different trucks from the same snapshot can lose one update. Source-confirmed, not exercised against Azure. | Store one control document per truck or use conditional patch/retry. |

## UI/UX improvements

These are product improvements, separate from the defects above.

1. **Put active incidents first.** Show a compact active-alert queue near the top, then a bounded/paginated history. The desktop screenshot shows 50 rows stretching the health card into a large empty column and pushing controls below a long scroll. Link an alert's truck ID to selection on the map and details.
2. **Add a searchable fleet list or truck selector.** Map-only selection hides trucks without coordinates and makes overlapping markers difficult to select. Include waiting trucks and counts; the current header excludes the waiting category. Add “Fit fleet” and “Locate selected truck” actions.
3. **Make timestamps operationally useful.** Alert rows and ETA show time only. Include date, explicit timezone, relative age, and absolute timestamp on demand; alerts from different days are currently indistinguishable by displayed time.
4. **Improve chart inspection.** Add readable hover/focus values, a tabular alternative, selectable time windows, and visible gaps when a truck is offline. A connected line over a long missing interval should not imply continuous measurement.
5. **Clarify unavailable data.** “No alerts yet – the fleet is healthy” is too strong when trucks have never reported. “Collecting readings” should distinguish no samples from request failure. Show limits from reference data even before the first reading.
6. **Make controls predictable.** Show “Applying…” and success feedback for faults; prevent repeat submissions while pending. Consider a demo-mode section that does not occupy the normal dispatch workflow.
7. **Improve accessibility and visual hierarchy.** Keep the useful status letters, but test contrast of white text on yellow/gray/green badges. Use existing dark `STATUS.text` values where appropriate, visible keyboard focus, larger touch targets, and live announcements for mutation results. Remove F1/F4/FR labels from normal operation or move them into a course/demo help view.

## Architecture, operations, and test improvements

- **Bound database work.** `CosmosFleetRepository.list_alerts()` loads every historical alert before sorting/limiting in Python. `/alerts` polls every five seconds and health loads up to 10,000 after the same full query. Use server-side ordering, limits and continuation tokens; maintain daily aggregates. The local health request took about 3.5 seconds in a smoke check; this is a measurement, not a cloud performance claim.
- **Detect never-reporting trucks.** The watcher skips trucks with no first reading forever. Define an activation time/startup grace period so a truck that fails at startup can trigger a missing-data incident.
- **Label cost estimates as assumptions.** The hard-coded model does not consume the deployed SKU or actual billing and treats <=8,000 messages/day as zero cost. Six trucks at ten-second intervals generate 51,840 messages/day; Terraform's default SKU is F1. Configure capacity deliberately and display the configured plan, not an implied automatic upgrade. No current Azure pricing estimate was validated in this audit.
- **Separate credentials and strengthen local durability.** Certificate generation makes all private keys, including the CA key, mode 0644; simulator/router mounts expose the entire certificate directory. Use least-privilege per-service mounts and keep the CA private key out of runtime containers. Cosmos/Azurite Compose services have no declared persistent volumes, so recreate/down workflows need explicit persistence and restore expectations.
- **Make certificate rotation repeatable.** `register_azure_devices.sh` skips existing identities even if local thumbprints changed; rerunning certificate generation followed by registration can leave Azure trusting old certificates. Add an explicit rotation/update path without silently replacing a live identity.
- **Strengthen tests around actual failure boundaries.** Existing coverage focuses on nominal rules. Add replay, shuffled batches, malformed events, network recovery, concurrent Cosmos writes, partial API outage, slow polling, truck-switch history, stale-data indicators, active-alert retention and responsive-layout checks. In-memory alerts are shared mutable objects, unlike Cosmos serialization, so concurrency tests must use copies or the real repository.
- **Make live broker tests deterministic.** `test_truck_cannot_publish_as_another_truck` observes only topic names; legitimate TRK-002 traffic can fail the test. Match a unique payload/correlation ID. Keep incomplete test messages off the real ingestion pipeline.
- **Make simulator physics consistent.** Route progress uses the full journey duration while reported speed is capped before randomization; live readings exceeded the nominal 120km/h cap. Treat accelerated demo time explicitly, or derive movement and reported speed from the same velocity.

## Suggested implementation order

1. Protect write boundaries; validate and isolate invalid telemetry.
2. Fix monotonic/idempotent processing, concurrency and durable notification/archive recovery.
3. Correct chart identity, stale/error states, active-alert visibility and mutation refresh.
4. Fix mobile overflow and introduce fleet selection plus incident-first layout.
5. Correct cloud archive/email status semantics, database query growth and operational configuration.

## Artifacts

- [Backend reproduction script](reproduce_backend.py) and [observed results](backend-results.txt).
- [Browser reproduction script](reproduce_browser.cjs): uses the installed Playwright package from the neighboring `scribe11/e2e` workspace, a temporary static server and the existing local GreenOps API proxy. Its absolute workspace paths must be adapted elsewhere.
- [Desktop screenshot](desktop.png), [mobile screenshot](mobile.png), and [mobile active-alert overflow](mobile-alert.png). Screenshots capture the state at that moment; initial loading text in a screenshot alone is not evidence of an endpoint outage.
