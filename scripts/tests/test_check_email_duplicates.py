"""Unit tests for the read-only duplicate-email check (no Azure needed)."""
import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "check_email_duplicates", pathlib.Path(__file__).resolve().parents[1] / "check_email_duplicates.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)


def alert(truck, kind, started, workflow, attempts=1):
    return {"doc_type": "alert", "truck_id": truck, "type": kind, "started_at": started,
            "email_workflow_id": workflow, "email_attempts": attempts}


def test_one_run_per_alert_is_clean():
    alerts = [alert("TRK-005", "OFFLINE", "2026-11-21T01:16:00Z", "wf1"),
              alert("TRK-004", "DELAYED", "2026-11-21T01:41:00Z", "wf2")]
    runs = [("wf1", "2026-11-21T01:16:01Z"), ("wf2", "2026-11-21T01:41:01Z")]
    r = check.find_duplicates(alerts, runs)
    assert (r["alerts"], r["runs"], r["unlinked_runs"], r["repeated_attempts"]) == (2, 2, [], [])
    assert r["per_day"] == {"2026-11-21": [2, 2]}


def test_resent_alert_is_reported():
    # The 2026-10-10 pattern: one OFFLINE alert, many workflow runs, only the last one linked to the alert.
    alerts = [alert("TRK-002", "OFFLINE", "2026-10-10T21:54:00Z", "wf3", attempts=3)]
    runs = [("wf1", "2026-10-10T21:54:01Z"), ("wf2", "2026-10-10T21:55:01Z"), ("wf3", "2026-10-10T21:56:01Z")]
    r = check.find_duplicates(alerts, runs)
    assert [x[0] for x in r["unlinked_runs"]] == ["wf1", "wf2"]
    assert r["repeated_attempts"] == [("TRK-002", "OFFLINE", "2026-10-10T21:54:00Z", 3)]


def test_since_ignores_history_before_a_fix_and_non_alert_documents():
    alerts = [alert("TRK-002", "OFFLINE", "2026-10-10T21:54:00Z", "wf3", attempts=3),
              {"doc_type": "truck_state", "truck_id": "TRK-001"},
              alert("TRK-005", "OFFLINE", "2026-11-21T01:16:00Z", "wf9")]
    runs = [("wf1", "2026-10-10T21:54:01Z"), ("wf9", "2026-11-21T01:16:01Z")]
    r = check.find_duplicates(alerts, runs, since="2026-10-12")
    assert (r["alerts"], r["runs"], r["unlinked_runs"], r["repeated_attempts"]) == (1, 1, [], [])


def test_run_that_never_sent_is_not_a_duplicate():
    # 2026-10-18: a run failed at its claim step, so send-alert-email was skipped and nothing was sent.
    alerts = [alert("TRK-005", "OFFLINE", "2026-11-21T01:16:00Z", "wf9")]
    runs = [("wf0", "2026-10-18T13:54:37Z", False), ("wf9", "2026-11-21T01:16:01Z", None),
            ("wfX", "2026-11-21T01:17:01Z", True)]
    r = check.find_duplicates(alerts, runs)
    assert r["runs"] == 2 and [x[0] for x in r["unlinked_runs"]] == ["wfX"]
