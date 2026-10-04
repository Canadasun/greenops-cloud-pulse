"""Reference data (CARGO_PROFILE, ROUTE, TRUCK) loaded from the shared contracts folder."""
import json
import math
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "contracts"  # repo-root contracts/, copied into the container


def _dir() -> Path:
    return Path(os.getenv("CONTRACTS_DIR", DEFAULT_DIR))


@lru_cache
def cargo_profiles() -> dict:
    data = json.loads((_dir() / "cargo_profiles.json").read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


@lru_cache
def fleet() -> dict:
    return json.loads((_dir() / "fleet.json").read_text())


def destination(route_id: str):
    return tuple(fleet()["routes"][route_id]["waypoints"][-1])


def km_between(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))
