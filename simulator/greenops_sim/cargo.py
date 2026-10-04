"""Cargo profiles: the safe temperature and humidity range for each cargo type (CARGO_PROFILE)."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CargoProfile:
    cargo_type: str
    temp_min_c: float
    temp_max_c: float
    humidity_max_pct: float

    @property
    def mid_temp_c(self) -> float:
        return (self.temp_min_c + self.temp_max_c) / 2

    def is_breach(self, temp_c: float, humidity_pct: float) -> bool:
        """True when a reading is outside the safe range for this cargo (FR-05)."""
        return not (self.temp_min_c <= temp_c <= self.temp_max_c) or humidity_pct > self.humidity_max_pct


def load_profiles(path) -> dict:
    data = json.loads(Path(path).read_text())
    return {name: CargoProfile(name, v["temp_min_c"], v["temp_max_c"], v["humidity_max_pct"])
            for name, v in data.items() if not name.startswith("_")}
