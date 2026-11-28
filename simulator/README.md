# Truck simulator – Role 1 (Ying Song)

Simulates 6 refrigerated trucks. Each truck runs in its own process, follows a real route (e.g. Ottawa → Toronto)
and publishes one JSON message every 10 seconds to its own topic `devices/<truck_id>/messages/events/`,
using its own X.509 certificate (FR-01, FR-03, FR-04). The message format is `contracts/telemetry.schema.json`.

Fault scenarios (FR-02) are switched on through a small HTTP API on port 8090:

| Request | Effect |
|---|---|
| `POST /trucks/TRK-003/fault {"scenario":"compressor"}` | temperature rises 0.6 °C every reading |
| `… {"scenario":"humidity"}` | humidity rises 2 % every reading (stops at 99 %) – broken dehumidifier, added in Part 4 |
| `… {"scenario":"door"}` | `door_open` becomes true |
| `… {"scenario":"delay"}` | truck slows to 15 % speed, so it misses its ETA |
| `… {"scenario":"offline"}` | the truck stops sending |
| `DELETE /trucks/TRK-003/fault` | back to normal |

On Azure (and in the local stack) the trucks also read the faults chosen on the dashboard from the Fleet API
(`FAULTS_URL` = `/api/sim/trucks`, polled every `FAULTS_POLL_S` seconds with the trucks' own `FAULTS_READ_TOKEN`).
At the end of a planned run each truck sends one last reading marked `parked`, so its silence is not reported as OFFLINE.
The same truck code drives the 100-truck scale test in `load/`.

Tests: `python -m pytest` (32 tests: data contract, route, every fault including humidity, publish loop, reconnect back-off,
control API, remote faults, parked end of run).
