from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
SERVICES = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
# Images with a healthcheck of their own (Superset, Homepage) or no way to run one
# (VictoriaLogs: no shell, wget or curl).
NO_COMPOSE_HEALTHCHECK = {"victorialogs", "superset", "portal"}


def test_every_service_rotates_its_logs():
    for name, service in SERVICES.items():
        assert service["logging"]["options"] == {"max-size": "10m", "max-file": "3"}, name


def test_ports_bind_to_localhost_only():
    # cloudflared and SSM port forwarding reach the server's services on localhost.
    for name, service in SERVICES.items():
        assert all(port.startswith("127.0.0.1:") for port in service["ports"]), name


def test_healthchecks_where_the_image_can_run_them():
    assert {name for name, s in SERVICES.items() if "healthcheck" not in s} == NO_COMPOSE_HEALTHCHECK


def test_superset_restarts_forever_only_where_configured():
    # Locally a missing secret must not crash-loop; the server sets SUPERSET_RESTART.
    assert SERVICES["superset"]["restart"] == "${SUPERSET_RESTART:-on-failure:3}"
    assert all(s["restart"] == "unless-stopped" for name, s in SERVICES.items() if name != "superset")


def test_portal_checks_dagster_in_its_container_by_default():
    # Linux Docker can't reach a 127.0.0.1-bound port through host.docker.internal.
    portal = SERVICES["portal"]["environment"]
    assert portal["HOMEPAGE_VAR_DAGSTER_URL"] == "${PORTAL_DAGSTER_URL:-http://dagster:3000}"
