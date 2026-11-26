"""The scale-test tools themselves are tested, so a green load result can be trusted."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loadtest import percentile, summary  # noqa: E402
from make_fleet import make_fleet, write_contracts  # noqa: E402


def test_bigger_fleet_has_unique_trucks_on_known_routes(tmp_path):
    fleet = make_fleet(100)
    assert len({t["truck_id"] for t in fleet["trucks"]}) == 100 and fleet["trucks"][99]["truck_id"] == "TRK-101"
    assert "TRK-099" not in {t["truck_id"] for t in fleet["trucks"]}  # revoked on purpose by the security tests
    assert all(t["route_id"] in fleet["routes"] for t in fleet["trucks"])
    assert json.loads((write_contracts(20, tmp_path) / "fleet.json").read_text())["trucks"][:6] == make_fleet(6)["trucks"]


def test_percentile_and_summary():
    assert percentile([], 95) is None and percentile(list(range(1, 101)), 95) == 96
    good = summary([1.0, 2.0, 3.0], 600, 600, 0, 4.2, 100, 1)
    assert good["passed"] and good["messages_per_second"] == 10.0


def test_lost_messages_slow_delivery_or_a_missing_alert_fail_the_run():
    assert not summary([1.0], 600, 599, 0, 4.2, 100, 1)["passed"]
    assert not summary([12.0], 600, 600, 0, 4.2, 100, 1)["passed"]
    assert not summary([1.0], 600, 600, 0, None, 100, 1)["passed"]
    assert not summary([1.0], 600, 600, 2, 4.2, 100, 1)["passed"]
    assert not summary([1.0], 500, 500, 0, 4.2, 100, 1, expected=600)["passed"]  # trucks that never connected
