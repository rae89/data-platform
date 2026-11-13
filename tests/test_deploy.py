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
    """Dagster answers from `runs` (one value per check); `just update` is recorded."""
    state = {"runs": [0], "updates": [], "code": 0, "sleeps": []}

    def fake_active_runs(url):
        return state["runs"].pop(0) if len(state["runs"]) > 1 else state["runs"][0]

    def fake_update(commit):
        state["updates"].append(commit)
        return state["code"]

    monkeypatch.setattr(deploy, "active_runs", fake_active_runs)
    monkeypatch.setattr(deploy, "just_update", fake_update)
    return state


def run(state, *args):
    return deploy.main([COMMIT, *args], sleep=state["sleeps"].append)


def test_updates_when_idle(server, capsys):
    assert run(server) == 0
    assert server["updates"] == [COMMIT]
    assert "now on 0123456" in capsys.readouterr().out


def test_waits_for_runs_to_finish(server, capsys):
    server["runs"] = [2, 1, 0]
    assert run(server, "--poll-seconds", "5") == 0
    assert server["sleeps"] == [5, 5]
    assert server["updates"] == [COMMIT]
    assert "2 Dagster run(s) in progress" in capsys.readouterr().out


def test_gives_up_when_still_busy(server, capsys):
    server["runs"] = [1]
    assert run(server, "--wait-minutes", "0") == deploy.BUSY
    assert server["updates"] == []
    assert "re-run the deploy later" in capsys.readouterr().out


def test_updates_when_dagster_is_down(server, capsys):
    server["runs"] = [None]
    assert run(server) == 0
    assert server["updates"] == [COMMIT]
    assert "Dagster didn't answer" in capsys.readouterr().out


def test_reports_a_failed_update(server, capsys):
    server["code"] = 3
    assert run(server) == 3
    assert "failed with exit code 3" in capsys.readouterr().out


def test_just_update_runs_the_recipe(monkeypatch):
    calls = []

    def fake_run(args, check):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert deploy.just_update("abc") == 0
    assert calls == [["just", "update", "abc"]]


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
    assert sent["body"]["variables"]["statuses"] == ["STARTING", "STARTED", "CANCELING"]


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
