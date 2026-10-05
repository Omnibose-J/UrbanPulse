"""Cloud Monitoring: an e-mail channel and one alert policy that fires when any UrbanPulse Cloud Run job
execution fails. Idempotent: both are found by display name and created only when absent. Prints names only.

    python scripts/cloud/alerts.py --project <id> --email <address> [--plan]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

CHANNEL_NAME = "UrbanPulse operator e-mail"
POLICY_NAME = "UrbanPulse: a Cloud Run job execution failed"
API = "https://monitoring.googleapis.com/v3"


def token() -> str:
    out = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, shell=True)
    if out.returncode != 0 or not out.stdout.strip():
        sys.exit("gcloud auth print-access-token failed")
    return out.stdout.strip()


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}/{path}",
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")


def ensure_channel(project: str, email: str, plan: bool) -> str | None:
    listing = call("GET", f"projects/{project}/notificationChannels")
    for channel in listing.get("notificationChannels", []):
        if channel.get("displayName") == CHANNEL_NAME:
            print("exists  notification channel (e-mail)")
            return channel["name"]
    if plan:
        print("plan    create notification channel (e-mail)")
        return None
    created = call(
        "POST",
        f"projects/{project}/notificationChannels",
        {
            "type": "email",
            "displayName": CHANNEL_NAME,
            "labels": {"email_address": email},
            "enabled": True,
        },
    )
    print("created notification channel (e-mail)")
    return created["name"]


def ensure_policy(project: str, channel: str | None, plan: bool) -> None:
    listing = call("GET", f"projects/{project}/alertPolicies")
    for policy in listing.get("alertPolicies", []):
        if policy.get("displayName") == POLICY_NAME:
            print("exists  alert policy (job execution failed)")
            return
    if plan or channel is None:
        print("plan    create alert policy (job execution failed)")
        return
    call(
        "POST",
        f"projects/{project}/alertPolicies",
        {
            "displayName": POLICY_NAME,
            "combiner": "OR",
            "enabled": True,
            "notificationChannels": [channel],
            "documentation": {
                "content": (
                    "A scheduled UrbanPulse job (collect, forecast, evaluate, sync_holidays) or a by-hand "
                    "execution ended in failure. Read the log: docs/RUNBOOK.md section 3. "
                    "The next scheduled slot is the retry."
                ),
                "mimeType": "text/markdown",
            },
            "conditions": [
                {
                    "displayName": "any Cloud Run job attempt with result=failed",
                    "conditionThreshold": {
                        "filter": (
                            'resource.type = "cloud_run_job" AND '
                            'metric.type = "run.googleapis.com/job/completed_task_attempt_count" AND '
                            'metric.labels.result = "failed"'
                        ),
                        "aggregations": [
                            {
                                "alignmentPeriod": "300s",
                                "perSeriesAligner": "ALIGN_DELTA",
                                "crossSeriesReducer": "REDUCE_SUM",
                                "groupByFields": ["resource.labels.job_name"],
                            }
                        ],
                        "comparison": "COMPARISON_GT",
                        "thresholdValue": 0,
                        "duration": "0s",
                        "trigger": {"count": 1},
                    },
                }
            ],
            "alertStrategy": {"autoClose": "1800s"},
        },
    )
    print("created alert policy (job execution failed)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    channel = ensure_channel(args.project, args.email, args.plan)
    ensure_policy(args.project, channel, args.plan)


if __name__ == "__main__":
    main()
