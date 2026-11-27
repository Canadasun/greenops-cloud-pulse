#!/usr/bin/env python3
"""Read-only check that every alert email was sent once (Role 3 – Shi Wang; FR-08).

Compares the alert-email Logic App's run history with the alerts stored in Cosmos DB. Each alert keeps the ID of the
workflow run that sent it (email_workflow_id), so a run that no alert points to, or an alert with more than one send
attempt, is a possible duplicate email. On 2026-10-10 a retry loop re-sent single alerts up to 85 times; this check
shows whether anything like that has happened since.

Usage (signed in with az; needs only read access):
    python scripts/check_email_duplicates.py --since 2026-10-12
Exit code 1 when a possible duplicate is found, so it can gate a live check.
"""
import argparse
import collections
import json
import subprocess
import sys


def find_duplicates(alerts, runs, since=""):
    """alerts: stored alert documents; runs: (run_id, start_time[, sent]) of the email workflow, where sent=False marks
    a run whose send-alert-email step did not succeed (no email left it). Returns a report dict."""
    alerts = [a for a in alerts if a.get("doc_type", "alert") == "alert" and a.get("started_at", "") >= since]
    runs = [r for r in runs if r[1] >= since and (len(r) < 3 or r[2] is not False)]
    linked = {a["email_workflow_id"] for a in alerts if a.get("email_workflow_id")}
    unlinked = sorted((r for r in runs if r[0] not in linked), key=lambda r: r[1])
    repeated = sorted(((a["truck_id"], a["type"], a["started_at"], a["email_attempts"])
                       for a in alerts if (a.get("email_attempts") or 0) > 1), key=lambda x: x[2])
    per_day = collections.defaultdict(lambda: [0, 0])
    for a in alerts:
        per_day[a["started_at"][:10]][0] += 1
    for r in runs:
        per_day[r[1][:10]][1] += 1
    return {"alerts": len(alerts), "runs": len(runs), "unlinked_runs": unlinked,
            "repeated_attempts": repeated, "per_day": dict(sorted(per_day.items()))}


def _az(*args):
    return json.loads(subprocess.run(["az", *args, "-o", "json"], check=True, capture_output=True, text=True).stdout)


def _load(resource_group, account, workflow):
    sub = _az("account", "show")["id"]
    url = (f"https://management.azure.com/subscriptions/{sub}/resourceGroups/{resource_group}/providers/"
           f"Microsoft.Logic/workflows/{workflow}/runs")
    url_base, url = url, url + "?api-version=2019-05-01&$top=250"
    runs = []
    while url:
        page = _az("rest", "--method", "get", "--url", url)
        runs += [(r["name"], r["properties"]["startTime"], r["properties"]["status"]) for r in page["value"]]
        url = page.get("nextLink")
    key = _az("cosmosdb", "keys", "list", "-n", account, "-g", resource_group,
              "--type", "read-only-keys")["primaryReadonlyMasterKey"]
    from azure.cosmos import CosmosClient  # only needed for the live check
    endpoint = _az("cosmosdb", "show", "-n", account, "-g", resource_group)["documentEndpoint"]
    container = CosmosClient(endpoint, key).get_database_client("greenops").get_container_client("alerts")
    alerts = list(container.query_items("SELECT * FROM c WHERE c.doc_type = 'alert'", enable_cross_partition_query=True))
    linked = {x.get("email_workflow_id") for x in alerts}
    checked = []
    for run_id, start, status in runs:
        sent = None
        if run_id not in linked and status != "Succeeded":  # only unlinked, failed runs need a closer look
            actions = _az("rest", "--method", "get", "--url", url_base + f"/{run_id}/actions?api-version=2019-05-01")
            sent = any(x["name"] == "send-alert-email" and x["properties"]["status"] == "Succeeded" for x in actions["value"])
        checked.append((run_id, start, sent))
    return alerts, checked


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--resource-group", default="rg-greenops-demo-g3-cc")
    p.add_argument("--account", default="cosmos-greenops-demo-g3-eastus2")
    p.add_argument("--workflow", default="logic-greenops-demo-g3-alerts")
    p.add_argument("--since", default="", help="ISO date; older history is ignored (e.g. before a fix)")
    a = p.parse_args(argv)
    report = find_duplicates(*_load(a.resource_group, a.account, a.workflow), since=a.since)
    print(f"{'day':<11}{'alerts':>7}{'emails sent':>13}")
    for day, (n_alerts, n_runs) in report["per_day"].items():
        print(f"{day:<11}{n_alerts:>7}{n_runs:>13}")
    print(f"total: {report['alerts']} alerts, {report['runs']} email workflow runs")
    print(f"runs no alert points to: {len(report['unlinked_runs'])}")
    print(f"alerts with more than one send attempt: {len(report['repeated_attempts'])}")
    for row in report["repeated_attempts"][:20]:
        print("  ", *row)
    clean = not report["unlinked_runs"] and not report["repeated_attempts"]
    print("RESULT:", "one email per alert" if clean else "possible duplicate emails")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
