"""Shared data objects (Part 2, Figure 5): Alert, AlertType, AlertStatus and time helpers."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid


class AlertType(str, Enum):
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    DOOR_OPEN = "DOOR_OPEN"
    OFFLINE = "OFFLINE"
    DELAYED = "DELAYED"


class AlertStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


OPEN_STATUSES = (AlertStatus.ACTIVE.value, AlertStatus.ACKNOWLEDGED.value)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Alert:
    truck_id: str
    type: str
    details: str
    started_at: str
    last_seen_at: str
    status: str = AlertStatus.ACTIVE.value
    id: str = field(default_factory=lambda: "alt-" + uuid.uuid4().hex[:12])
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    email_sent_at: str | None = None
    email_seconds: float | None = None

    def to_doc(self) -> dict:
        return {**asdict(self), "doc_type": "alert"}

    @classmethod
    def from_doc(cls, d: dict) -> "Alert":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})
