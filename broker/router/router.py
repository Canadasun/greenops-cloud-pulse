"""Message router – local stand-in for Azure IoT Hub message routing (Role 2 – Marcelbriaud Wafotchoupe).

Subscribes to every truck topic as the 'router' identity and sends each message to two places (Part 2, Figure 7):
  ② the Alert Function (HTTP POST, in batches, with retries and a dead-letter folder)
  ③ the raw archive in Blob Storage (one JSON-lines file every ARCHIVE_INTERVAL_S seconds)
"""
import json
import logging
import os
import ssl
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone

log = logging.getLogger("router")
RETRIES = 3


def archive_blob_name(now, batch_id):
    return now.strftime("telemetry/%Y/%m/%d/%H/%M-") + f"{batch_id}.jsonl"


class Router:
    def __init__(self, send_to_alerts, archive, max_batch=50, sleep=time.sleep):
        self.send_to_alerts, self.archive, self.max_batch, self.sleep = send_to_alerts, archive, max_batch, sleep
        self.pending, self.archive_buffer = [], []
        self.lock = threading.Lock()
        self.stats = {"received": 0, "delivered": 0, "invalid": 0, "dead_lettered": 0, "archived": 0}

    def on_message(self, topic, payload: bytes):
        try:
            msg = json.loads(payload)
            device = topic.split("/")[1]
            if msg.get("truck_id") != device:
                raise ValueError(f"payload truck_id {msg.get('truck_id')} does not match topic device {device}")
        except (ValueError, IndexError) as e:
            self.stats["invalid"] += 1
            log.warning("skipped invalid message on %s: %s", topic, e)
            return
        with self.lock:
            self.stats["received"] += 1
            self.pending.append(msg)
            self.archive_buffer.append(msg)

    def flush_alerts(self):
        with self.lock:
            batch, self.pending = self.pending, []
        for i in range(0, len(batch), self.max_batch):
            chunk = batch[i:i + self.max_batch]
            for attempt in range(1, RETRIES + 1):
                try:
                    self.send_to_alerts(chunk)
                    self.stats["delivered"] += len(chunk)
                    break
                except Exception as e:  # noqa: BLE001 – any delivery failure is retried
                    log.warning("alert delivery failed (attempt %d/%d): %s", attempt, RETRIES, e)
                    self.sleep(2 ** attempt)
            else:
                self.stats["dead_lettered"] += len(chunk)
                name = "deadletter/" + archive_blob_name(datetime.now(timezone.utc), uuid.uuid4().hex[:8]).split("/", 1)[1]
                self.archive.upload(name, "\n".join(json.dumps(m) for m in chunk).encode())

    def flush_archive(self, now=None):
        with self.lock:
            batch, self.archive_buffer = self.archive_buffer, []
        if not batch:
            return None
        name = archive_blob_name(now or datetime.now(timezone.utc), uuid.uuid4().hex[:8])
        self.archive.upload(name, "\n".join(json.dumps(m, separators=(",", ":")) for m in batch).encode())
        self.stats["archived"] += len(batch)
        log.info("archived %d messages to %s", len(batch), name)
        return name


class HttpAlertEndpoint:
    def __init__(self, url, key=None):
        self.url, self.key = url, key

    def __call__(self, messages):
        req = urllib.request.Request(self.url, data=json.dumps(messages).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"x-functions-key": self.key} if self.key else {})})
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status >= 300:
                raise ConnectionError(f"HTTP {r.status}")


class BlobArchive:
    def __init__(self, connection_string, container):
        from azure.storage.blob import BlobServiceClient
        self.container = BlobServiceClient.from_connection_string(connection_string).get_container_client(container)
        for _ in range(30):
            try:
                if not self.container.exists():
                    self.container.create_container()
                break
            except Exception as e:  # noqa: BLE001 – storage may still be starting
                log.info("waiting for blob storage: %s", e)
                time.sleep(2)

    def upload(self, name, data):
        self.container.upload_blob(name, data, overwrite=True)


def main():
    import paho.mqtt.client as mqtt
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    cert_dir = os.getenv("CERT_DIR", "/certs")
    router = Router(HttpAlertEndpoint(os.environ["ALERT_FUNCTION_URL"], os.getenv("ALERT_FUNCTION_KEY")),
                    BlobArchive(os.environ["STORAGE_CONNECTION_STRING"], os.getenv("ARCHIVE_CONTAINER", "telemetry-archive")))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="router", protocol=mqtt.MQTTv5)
    client.tls_set(ca_certs=f"{cert_dir}/ca.crt", certfile=f"{cert_dir}/router.crt", keyfile=f"{cert_dir}/router.key",
                   tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.on_connect = lambda c, u, f, rc, p=None: (log.info("connected: %s", rc), c.subscribe("devices/+/messages/events/", qos=1))
    client.on_message = lambda c, u, m: router.on_message(m.topic, m.payload)
    while True:
        try:
            client.connect(os.getenv("MQTT_HOST", "mosquitto"), int(os.getenv("MQTT_PORT", "8883")))
            break
        except OSError as e:
            log.info("waiting for broker: %s", e)
            time.sleep(3)
    client.loop_start()
    archive_every = float(os.getenv("ARCHIVE_INTERVAL_S", "300"))
    last_archive = time.monotonic()
    while True:
        router.flush_alerts()
        if time.monotonic() - last_archive >= archive_every:
            router.flush_archive()
            last_archive = time.monotonic()
        time.sleep(float(os.getenv("FORWARD_INTERVAL_S", "1")))


if __name__ == "__main__":
    main()
