"""One simulated refrigerated truck (Role 1 – Ying Song).

The truck moves along its route, reads simulated sensors and builds a TelemetryMessage that follows
contracts/telemetry.schema.json. Fault scenarios (FR-02) change the readings so every alert can be tested.
"""
import random
from datetime import datetime, timedelta, timezone

SCENARIOS = ("none", "compressor", "door", "delay", "offline")
COMPRESSOR_RISE_C = 0.6        # temperature gained per reading while the compressor is broken
DELAY_SPEED_FACTOR = 0.15      # a delayed truck moves at 15 % of its normal speed
AMBIENT_C = 24.0               # a broken compressor warms the cargo up to the outside temperature, not beyond


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TruckSimulator:
    def __init__(self, truck_id, route, profile, clock=None, journey_s=3600, seed=None):
        self.truck_id = truck_id
        self.route = route
        self.profile = profile
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.journey_s = journey_s
        self.rng = random.Random(seed)
        self.scenario = "none"
        self.started = self.clock()
        self.scheduled_eta = self.started + timedelta(seconds=journey_s)
        self.progress = 0.0
        self.temp_c = profile.mid_temp_c
        self.humidity_pct = min(60.0, profile.humidity_max_pct - 10)
        self._last = self.started

    @property
    def topic(self) -> str:
        """The only topic this truck is allowed to publish to (FR-04, IoT Hub device-to-cloud topic)."""
        return f"devices/{self.truck_id}/messages/events/"

    @property
    def arrived(self) -> bool:
        return self.progress >= 1.0

    def inject_fault(self, scenario: str):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}; use one of {SCENARIOS}")
        self.scenario = scenario

    def clear_fault(self):
        self.scenario = "none"

    def should_publish(self) -> bool:
        return self.scenario != "offline"

    def _move(self, now):
        dt = (now - self._last).total_seconds()
        self._last = now
        factor = DELAY_SPEED_FACTOR if self.scenario == "delay" else 1.0
        self.progress = min(1.0, self.progress + factor * dt / self.journey_s)
        if self.arrived:
            return 0.0
        normal_kmh = self.route.length_km / (self.journey_s / 3600)
        return min(120.0, normal_kmh) * factor * self.rng.uniform(0.9, 1.05)

    def _sense(self):
        p = self.profile
        if self.scenario == "compressor":
            self.temp_c = min(self.temp_c + COMPRESSOR_RISE_C, AMBIENT_C)
        else:  # refrigeration pulls the temperature back towards the middle of the safe range
            span = p.temp_max_c - p.temp_min_c
            self.temp_c += (p.mid_temp_c - self.temp_c) * 0.3 + self.rng.uniform(-0.08, 0.08) * span
            self.temp_c = min(max(self.temp_c, p.temp_min_c + 0.1 * span), p.temp_max_c - 0.1 * span)
        self.humidity_pct = min(max(self.humidity_pct + self.rng.uniform(-1.5, 1.5), 40.0), p.humidity_max_pct - 3)

    def next_reading(self) -> dict:
        now = self.clock()
        speed = self._move(now)
        self._sense()
        lat, lon = self.route.position_at(self.progress)
        return {
            "truck_id": self.truck_id,
            "route_id": self.route.route_id,
            "timestamp": _iso(now),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "speed_kmh": round(speed, 1),
            "temp_c": round(self.temp_c, 2),
            "humidity_pct": round(self.humidity_pct, 1),
            "door_open": self.scenario == "door",
            "cargo_type": self.profile.cargo_type,
            "temp_min_c": self.profile.temp_min_c,
            "temp_max_c": self.profile.temp_max_c,
            "scheduled_eta": _iso(self.scheduled_eta),
        }
