# Ingestion – Role 2 (Marcelbriaud Wafotchoupe)

Local stand-in for **Azure IoT Hub** (Part 2, Figure 7, steps ① – ③).

* `mosquitto.conf` – MQTT broker on port 8883 with **mutual TLS**: a client must present a certificate signed by the
  GreenOps Device CA (FR-03). The certificate's common name (CN) is the device name.
* `acl` – a truck may only publish to `devices/<its own id>/messages/events/` (FR-04).
* `crl.pem` (generated) – revoked certificates are refused; `scripts/revoke_cert.sh TRK-004` then `docker compose kill -s HUP mosquitto`.
* `router/` – stand-in for IoT Hub **message routing**: sends every message to the Alert Function (batches of 50,
  3 retries, then `deadletter/`) and writes the raw archive to Blob Storage every 5 minutes as JSON lines.
* Certificates are created by `scripts/make_certs.sh` into `certs/` and are never committed.

Tests: `tests/test_broker_security.py` (5 tests against the running broker: registered truck accepted, unknown CA refused,
no certificate refused, cannot publish as another truck, cannot read other trucks) and `router/tests` (8 unit tests).
Revocation was verified manually and is also part of the end-to-end tests.
