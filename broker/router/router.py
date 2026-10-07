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
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger("router")
RETRIES = 3


def archive_blob_name(now, batch_id):
    return now.strftime("telemetry/%Y/%m/%d/%H/%M-") + f"{batch_id}.jsonl"


class Router:
    """SQLite spool: acknowledge MQTT only after durable receipt, retire after both sinks."""
    def __init__(self, send_to_alerts, archive, max_batch=50, sleep=time.sleep, spool_path=":memory:"):
        self.send_to_alerts, self.archive, self.max_batch, self.sleep = send_to_alerts, archive, max_batch, sleep
        self.lock = threading.RLock()
        self.db = sqlite3.connect(spool_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, payload TEXT, received TEXT, delivered INTEGER DEFAULT 0, archived INTEGER DEFAULT 0)")
        self.db.execute("CREATE TABLE IF NOT EXISTS quarantine (id TEXT PRIMARY KEY, topic TEXT, payload TEXT, reason TEXT)")
        self.db.commit()
        self.stats = {"received": 0, "delivered": 0, "invalid": 0, "dead_lettered": 0, "archived": 0}

    @property
    def pending(self):
        return [json.loads(r[1]) for r in self._rows("delivered")]

    @property
    def archive_buffer(self):
        return [json.loads(r[1]) for r in self._rows("archived")]

    def _rows(self, sink):
        with self.lock:
            return self.db.execute(f"SELECT id,payload,received FROM messages WHERE {sink}=0 ORDER BY id LIMIT 500", ()).fetchall()

    def _done(self, rows, sink):
        with self.lock, self.db:
            self.db.executemany(f"UPDATE messages SET {sink}=1 WHERE id=?", [(r[0],) for r in rows])
            self.db.execute("DELETE FROM messages WHERE delivered=1 AND archived=1")

    def on_message(self, topic, payload: bytes):
        try:
            if len(payload) > 16384:
                raise ValueError("event exceeds 16 KiB")
            msg = json.loads(payload)
            parts = topic.split("/")
            if not isinstance(msg, dict) or len(parts) != 5 or parts[0] != "devices" or parts[2:] != ["messages", "events", ""]:
                raise ValueError("invalid topic or message object")
            if msg.get("truck_id") != parts[1]:
                raise ValueError("payload identity does not match device topic")
        except (ValueError, IndexError) as e:
            with self.lock, self.db:
                self.db.execute("INSERT OR IGNORE INTO quarantine VALUES (?,?,?,?)", (hashlib.sha256(payload).hexdigest(), topic, payload[:16384].decode(errors="replace"), str(e)))
            self.stats["invalid"] += 1
            log.warning("quarantined invalid message on %s: %s", topic, e)
            return
        with self.lock, self.db:
            self.db.execute("INSERT INTO messages(payload,received) VALUES (?,?)", (json.dumps(msg, separators=(",", ":")), datetime.now(timezone.utc).isoformat()))
            self.stats["received"] += 1

    def flush_alerts(self):
        rows = self._rows("delivered")
        for i in range(0, len(rows), self.max_batch):
            group = rows[i:i + self.max_batch]
            chunk = [json.loads(r[1]) for r in group]
            for attempt in range(1, RETRIES + 1):
                try:
                    self.send_to_alerts(chunk)
                    self._done(group, "delivered")
                    self.stats["delivered"] += len(chunk)
                    break
                except Exception as e:
                    log.warning("alert delivery attempt %d/%d failed: %s", attempt, RETRIES, e)
                    self.sleep(2 ** attempt)
            else:
                data = "\n".join(r[1] for r in group).encode()
                name = "deadletter/" + hashlib.sha256(data).hexdigest() + ".jsonl"
                try:
                    self.archive.upload(name, data)
                except Exception as e:
                    log.warning("dead-letter storage unavailable; retained in spool: %s", e)
                    return
                self._done(group, "delivered")
                self.stats["dead_lettered"] += len(chunk)

    def flush_archive(self, now=None):
        rows = self._rows("archived")
        if not rows:
            return None
        data = "\n".join(r[1] for r in rows).encode()
        name = archive_blob_name(now or datetime.fromisoformat(rows[0][2]), hashlib.sha256(data).hexdigest()[:24])
        try:
            self.archive.upload(name, data)
        except Exception as e:
            log.warning("archive unavailable; retained in spool: %s", e)
            return None
        self._done(rows, "archived")
        self.stats["archived"] += len(rows)
        return name


class HttpAlertEndpoint:
    def __init__(self, url, key=None):
        self.url, self.key = url, key

    def __call__(self, messages):
        req = urllib.request.Request(self.url, data=json.dumps(messages).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + self.key} if self.key else {})})
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
    logging.getLogger("azure").setLevel(logging.WARNING)  # hide SDK request/response logs
    cert_dir = os.getenv("CERT_DIR", "/certs")
    router = Router(HttpAlertEndpoint(os.environ["ALERT_FUNCTION_URL"], os.environ["INGESTION_TOKEN"]),
                    BlobArchive(os.environ["STORAGE_CONNECTION_STRING"], os.getenv("ARCHIVE_CONTAINER", "telemetry-archive")),
                    spool_path=os.getenv("SPOOL_PATH", "/data/router.sqlite"))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="router", protocol=mqtt.MQTTv311, clean_session=False, manual_ack=True)
    client.tls_set(ca_certs=f"{cert_dir}/ca.crt", certfile=f"{cert_dir}/router.crt", keyfile=f"{cert_dir}/router.key",
                   tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.on_connect = lambda c, u, f, rc, p=None: (log.info("connected: %s", rc), c.subscribe("devices/+/messages/events/", qos=1))
    def receive(c, u, m):
        try:
            router.on_message(m.topic, m.payload)
            c.ack(m.mid, m.qos)
        except Exception:
            log.exception("durable receipt failed; restarting without acknowledging MQTT")
            os._exit(1)
    client.on_message = receive
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
