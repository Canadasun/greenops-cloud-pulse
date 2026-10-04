# Truck simulator – Role 1 (Ying Song)

Simulates 6 refrigerated trucks. Each truck runs in its own process, follows a real route (e.g. Ottawa → Toronto)
and publishes one JSON message every 10 seconds to its own topic `devices/<truck_id>/messages/events/`,
using its own X.509 certificate (FR-01, FR-03, FR-04). The message format is `contracts/telemetry.schema.json`.

Fault scenarios (FR-02) are switched on through a small HTTP API on port 8090:

| Request | Effect |
|---|---|
| `POST /trucks/TRK-003/fault {"scenario":"compressor"}` | temperature rises 0.6 °C every reading |
| `… {"scenario":"door"}` | `door_open` becomes true |
| `… {"scenario":"delay"}` | truck slows to 15 % speed, so it misses its ETA |
| `… {"scenario":"offline"}` | the truck stops sending |
| `DELETE /trucks/TRK-003/fault` | back to normal |

Tests: `python -m pytest` (17 tests: data contract, route, every fault, publish loop, reconnect back-off, control API).
