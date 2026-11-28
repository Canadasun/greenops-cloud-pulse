# Scale test – NFR-04 (Part 4: Ying Song, Marcelbriaud Wafotchoupe, Durmusali Unal)

Part 1 promised the system would handle **100 trucks** (NFR-04). These tools prove it with numbers, using the same truck,
broker and Functions code as the six-truck demo – only the reference data changes.

| File | Does |
|---|---|
| `make_fleet.py` | writes a 100-truck fleet (same routes and cargo types) to `load/contracts-100/` (not committed) |
| `compose.load.yml` | runs the local stack with that fleet instead of the demo one |
| `loadtest.py` | N trucks, each with its own certificate and connection, one reading every 10 s; reports readings stored, time until visible on the fleet view (p50/p95) and whether an alert email still arrives in time |
| `benchmark.py` | counts database requests and time per operation against Cosmos DB, so two versions of the code can be compared |
| `test_load.py` | unit tests of the tools (3) |

```bash
python load/make_fleet.py 100 load/contracts-100
for i in $(seq -f %03g 7 100); do bash scripts/issue_cert.sh TRK-$i; done
docker compose -p greenops-load -f docker-compose.yml -f load/compose.load.yml up -d --build --scale simulator=0
python load/loadtest.py --trucks 100 --minutes 5
# Azure: add --iothub <hub>.azure-devices.net --api https://<function app>/api (6,000 messages in 10 minutes; F1 allows 8,000 a day)
```

Results (2026-11-25, local): **3,000 of 3,000** readings stored, visible in **2.2 s at p95**, alert email in **1.1 s**.
Benchmark with 20 ms database latency: one round of 100 trucks took **13.4 s** with the Part 3 code – longer than the 10 s
between readings, so it would fall behind – and **2.4 s** after the Part 4 changes (fleet snapshot, one transaction per truck,
batched writes). Evidence files are kept with the Part 4 report.
