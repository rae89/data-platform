import importlib.util
import io
import json
import subprocess
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("deploy", ROOT / "infra" / "server" / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

COMMIT = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def server(monkeypatch):
    """Dagster answers from `runs` (one value per check); commands are recorded."""
    state = {"runs": [0], "commands": [], "codes": {}, "sleeps": []}

    def fake_active_runs(url):
        return state["runs"].pop(0) if len(state["runs"]) > 1 else state["runs"][0]

    def fake_run(args):
        state["commands"].append(args)
        return state["codes"].get(args[1], 0)

    monkeypatch.setattr(deploy, "active_runs", fake_active_runs)
    monkeypatch.setattr(deploy, "run", fake_run)
    return state


MERGE = ["git", "merge", "--ff-only", "--quiet", COMMIT]
PULL = ["just", "update-pull", COMMIT]
UP = ["docker", "compose", "up", "-d"]


def run(state, *args):
    return deploy.main([COMMIT, *args], sleep=state["sleeps"].append)


def test_pulls_then_restarts_when_idle(server, capsys):
    assert run(server) == 0
    assert server["commands"] == [MERGE, PULL, UP]
    assert "now on 0123456" in capsys.readouterr().out


def test_waits_for_runs_to_finish(server, capsys):
    server["runs"] = [2, 1, 0]
    assert run(server, "--poll-seconds", "5") == 0
    assert server["sleeps"] == [5, 5]
    assert server["commands"] == [MERGE, PULL, UP]
    assert "2 Dagster run(s) in progress" in capsys.readouterr().out


def test_gives_up_when_still_busy(server, capsys):
    server["runs"] = [1]
    assert run(server, "--wait-minutes", "0") == deploy.BUSY
    assert server["commands"] == [MERGE, PULL]
    assert "re-run the deploy later" in capsys.readouterr().out


def test_a_slow_answer_during_a_run_is_not_down(server):
    server["runs"] = [1, None, None, 1, 0]
    assert run(server) == 0
    assert len(server["sleeps"]) == 4
    assert server["commands"] == [MERGE, PULL, UP]


def test_updates_when_dagster_stays_down(server, capsys):
    server["runs"] = [None]
    assert run(server) == 0
    assert len(server["sleeps"]) == deploy.DOWN_AFTER - 1
    assert server["commands"] == [MERGE, PULL, UP]
    assert "updating anyway" in capsys.readouterr().out


def test_stops_when_the_pull_fails(server, capsys):
    server["codes"] = {"update-pull": 3}
    assert run(server) == 3
    assert server["commands"] == [MERGE, PULL]
    assert "`just update-pull` failed with exit code 3" in capsys.readouterr().out


def test_stops_when_the_fast_forward_fails(server, capsys):
    server["codes"] = {"merge": 128}
    assert run(server) == 128
    assert server["commands"] == [MERGE]
    assert "`git merge` failed with exit code 128" in capsys.readouterr().out


def test_reports_a_failed_restart(server, capsys):
    server["codes"] = {"compose": 4}
    assert run(server) == 4
    assert "`docker compose up` failed with exit code 4" in capsys.readouterr().out


def test_run_returns_the_exit_code(monkeypatch):
    calls = []

    def fake_run(args, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert deploy.run(["just", "update-pull", "abc"]) == 2
    assert calls == [["just", "update-pull", "abc"]]


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ({"data": {"runsOrError": {"__typename": "Runs", "results": [{"runId": "a"}]}}}, 1),
        ({"data": {"runsOrError": {"__typename": "Runs", "results": []}}}, 0),
        ({"data": {"runsOrError": {"__typename": "PythonError"}}}, None),
        ({"errors": [{"message": "bad query"}]}, None),
    ],
)
def test_active_runs_reads_dagster(monkeypatch, answer, expected):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data)
        return FakeResponse(json.dumps(answer).encode())

    monkeypatch.setattr(deploy.urllib.request, "urlopen", fake_urlopen)
    assert deploy.active_runs("http://dagster:3000") == expected
    assert sent["url"] == "http://dagster:3000/graphql"
    assert sent["body"]["variables"]["statuses"] == ["NOT_STARTED", "STARTING", "STARTED", "CANCELING"]


def test_active_runs_is_none_when_dagster_is_unreachable(monkeypatch):
    def refuse(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(deploy.urllib.request, "urlopen", refuse)
    assert deploy.active_runs("http://localhost:1") is None


def test_ssm_document_runs_this_script_from_the_deployed_commit():
    # infra/deploy.tf pipes this file from the commit being deployed into python3.
    document = (ROOT / "infra" / "deploy.tf").read_text()
    assert "git show {{ commit }}:infra/server/deploy.py | python3 - {{ commit }}" in document
    assert 'allowedPattern = "^[0-9a-f]{40}$"' in document


def test_deploy_job_runs_after_the_image_build():
    workflow = (ROOT / ".github" / "workflows" / "images.yml").read_text()
    deploy_job = workflow.split("\n  deploy:\n", 1)[1]
    assert "needs: build" in deploy_job
    assert "commit=${{ github.sha }}" in deploy_job
    # A newer push may cancel a build, never a deploy that is in progress.
    assert "cancel-in-progress: true" not in workflow.split("\njobs:\n", 1)[0]
    assert "cancel-in-progress: false" in deploy_job


def test_images_are_tagged_with_the_full_commit():
    # `just update-pull` pulls sha-<full commit>.
    assert "type=sha,format=long" in (ROOT / ".github" / "workflows" / "images.yml").read_text()


def test_role_trusts_the_immutable_subject_on_main():
    # GitHub sends repo:<owner>@<id>/<name>@<id>:ref:... for this repo; a plain
    # repo:<owner>/<name> condition makes every deploy fail to assume the role.
    variables = (ROOT / "infra" / "variables.tf").read_text()
    assert 'default     = "repo:rae89@9400794/data-platform@1448576146"' in variables
    document = (ROOT / "infra" / "deploy.tf").read_text()
    assert ':ref:refs/heads/main"' in document and "var.github_oidc_sub_prefix" in document
