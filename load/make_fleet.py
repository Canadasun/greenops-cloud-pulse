"""Builds a larger fleet for the scale test (Role 1 – Ying Song): the same routes and cargo types, N trucks, no code changes.

    python load/make_fleet.py 100 load/contracts-100      # writes fleet.json, cargo_profiles.json and the message schema
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESERVED = {"TRK-099", "TRK-666"}  # the security tests need these two to be refused


def make_fleet(n, source=ROOT / "contracts"):
    fleet = json.loads((Path(source) / "fleet.json").read_text())
    model = fleet["trucks"]
    ids = [f"TRK-{i:03d}" for i in range(1, n + len(RESERVED) + 1) if f"TRK-{i:03d}" not in RESERVED][:n]
    fleet["trucks"] = [{**model[i % len(model)], "truck_id": truck_id} for i, truck_id in enumerate(ids)]
    return fleet


def write_contracts(n, target, source=ROOT / "contracts"):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for f in Path(source).glob("*.json"):
        shutil.copy(f, target)
    (target / "fleet.json").write_text(json.dumps(make_fleet(n, source), indent=1))
    return target


if __name__ == "__main__":
    print(write_contracts(int(sys.argv[1]), sys.argv[2]))
