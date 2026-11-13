#!/usr/bin/env python3
"""Update the server to one commit on main, once no Dagster run is in progress.

CI's "deploy" job (.github/workflows/images.yml) runs this on the server through SSM
Run Command (infra/deploy.tf) after both images for the commit are built:

1. Waits while a Dagster run is in progress (up to 60 minutes), so an update never
   kills a run.
2. Runs `just update <commit>`: fast-forward, pull the images, restart what changed.

By hand, in the checkout on the server: `python3 infra/server/deploy.py <commit>`.
Standard library only: the server has the system python3, not uv.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence

DAGSTER_URL = "http://localhost:3000"
# Statuses that mean a run holds the warehouse right now. QUEUED runs survive a restart.
ACTIVE_STATUSES = ("STARTING", "STARTED", "CANCELING")
RUNS_QUERY = (
    "query ActiveRuns($statuses: [RunStatus!]) {"
    " runsOrError(filter: {statuses: $statuses}) {"
    " __typename ... on Runs { results { runId } } } }"
)
BUSY = 75  # EX_TEMPFAIL: still busy after the wait; re-run the deploy job later


def log(message: str) -> None:
    print(f"deploy: {message}", flush=True)


def active_runs(dagster_url: str) -> int | None:
    """Number of Dagster runs in progress, or None when Dagster can't be asked."""
    body = json.dumps(
        {"query": RUNS_QUERY, "variables": {"statuses": list(ACTIVE_STATUSES)}}
    ).encode()
    request = urllib.request.Request(
        f"{dagster_url}/graphql",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    runs = (data.get("data") or {}).get("runsOrError") or {}
    if runs.get("__typename") != "Runs":
        return None
    return len(runs.get("results") or [])


def just_update(commit: str) -> int:
    """The same update as by hand; its output goes to the deploy job's log."""
    return subprocess.run(["just", "update", commit], check=False).returncode


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("commit", help="commit on main to update to")
    parser.add_argument("--dagster-url", default=DAGSTER_URL)
    parser.add_argument("--wait-minutes", type=float, default=60)
    parser.add_argument("--poll-seconds", type=float, default=30)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, sleep=time.sleep) -> int:
    args = parse_args(argv)
    short = args.commit[:7]
    deadline = time.monotonic() + args.wait_minutes * 60
    while (runs := active_runs(args.dagster_url)) and time.monotonic() < deadline:
        log(f"{runs} Dagster run(s) in progress; checking again in {args.poll_seconds:g}s")
        sleep(args.poll_seconds)
    if runs:
        log(f"still {runs} run(s) after {args.wait_minutes:g} minutes; re-run the deploy later")
        return BUSY
    if runs is None:
        log("Dagster didn't answer; updating anyway")

    log(f"updating to {short}")
    code = just_update(args.commit)
    log(f"now on {short}" if code == 0 else f"`just update` failed with exit code {code}")
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
