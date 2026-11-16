#!/usr/bin/env python3
"""Update the server to one commit on main, once no Dagster run is in progress.

CI's "deploy" job (.github/workflows/images.yml) runs this on the server through SSM
Run Command (infra/deploy.tf) after both images for the commit are built:

1. Fast-forwards to the commit, then runs its `just update-pull`: pull its images.
2. Waits while a Dagster run is in progress (up to 60 minutes), so an update never
   kills a run.
3. Runs `docker compose up -d` right after the last check: restart what changed.

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
# Statuses that mean a run holds, or is about to hold, the warehouse. QUEUED runs
# survive a restart; NOT_STARTED ones (submitted, not launched yet) may not.
ACTIVE_STATUSES = ("NOT_STARTED", "STARTING", "STARTED", "CANCELING")
RUNS_QUERY = (
    "query ActiveRuns($statuses: [RunStatus!]) {"
    " runsOrError(filter: {statuses: $statuses}) {"
    " __typename ... on Runs { results { runId } } } }"
)
BUSY = 75  # EX_TEMPFAIL: still busy after the wait; re-run the deploy job later
# A slow or erroring Dagster during a run must not count as "down": only this many
# failed checks in a row do.
DOWN_AFTER = 3


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


def run(args: list[str]) -> int:
    """Runs a command in the checkout; its output goes to the deploy job's log."""
    return subprocess.run(args, check=False).returncode


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("commit", help="commit on main to update to")
    parser.add_argument("--dagster-url", default=DAGSTER_URL)
    parser.add_argument("--wait-minutes", type=float, default=60)
    parser.add_argument("--poll-seconds", type=float, default=30)
    return parser.parse_args(argv)


def wait_until_idle(args: argparse.Namespace, sleep) -> int | None:
    """0 when idle, None when Dagster stayed down, else the runs still in progress."""
    deadline = time.monotonic() + args.wait_minutes * 60
    failures = 0
    while True:
        runs = active_runs(args.dagster_url)
        failures = failures + 1 if runs is None else 0
        if runs == 0 or failures >= DOWN_AFTER or time.monotonic() >= deadline:
            return runs
        log(
            "Dagster didn't answer" if runs is None else f"{runs} Dagster run(s) in progress"
        )
        sleep(args.poll_seconds)


def main(argv: Sequence[str] | None = None, sleep=time.sleep) -> int:
    args = parse_args(argv)
    short = args.commit[:7]
    log(f"pulling {short}")
    # Fast-forward first: `just update-pull` must come from the new justfile, not the old one.
    # services.yaml is generated and holds public links on the server (`just portal-public`).
    for command in (
        ["git", "checkout", "--", "portal/homepage/services.yaml"],
        ["git", "merge", "--ff-only", "--quiet", args.commit],
        ["just", "update-pull", args.commit],
    ):
        if code := run(command):
            log(f"`{' '.join(command[:2])}` failed with exit code {code}")
            return code

    runs = wait_until_idle(args, sleep)
    if runs:
        log(f"still {runs} run(s) after {args.wait_minutes:g} minutes; re-run the deploy later")
        return BUSY
    if runs is None:
        log("Dagster didn't answer; updating anyway")

    # Straight after the last check: a run a sensor starts in between would be killed.
    code = run(["docker", "compose", "up", "-d"])
    log(f"now on {short}" if code == 0 else f"`docker compose up` failed with exit code {code}")
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
