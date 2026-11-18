import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("render_landing", ROOT / "portal" / "render_landing.py")
render_landing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_landing)

URL = "https://dp-{name}.example.com"
CATALOG = {
    "components": [
        {
            "name": "Dagster",
            "group": "Orchestration",
            "description": "Runs <b>& assets",
            "url": "http://localhost:3000",
            "public": "dagster",
        },
        {
            "name": "dlt dashboard",
            "group": "Orchestration",
            "description": "local",
            "url": "http://localhost:2718",
        },
        {
            "name": "Landing page",
            "group": "Links",
            "description": "this page",
            "url": "https://x",
            "public": "",
        },
    ]
}
TEMPLATE = '<a href="$sign_in_url">Sign in</a><ul>$components</ul>'


def test_sign_in_points_at_public_portal():
    assert 'href="https://dp-portal.example.com/"' in render_landing.render(TEMPLATE, CATALOG, URL)


def test_sign_in_url_rejects_missing_or_bad_value():
    for bad in (None, "", "https://example.com"):
        with pytest.raises(ValueError):
            render_landing.sign_in_url(bad)


def test_lists_only_public_components():
    html = render_landing.render(TEMPLATE, CATALOG, URL)
    assert "Dagster" in html and "dlt dashboard" not in html and "Landing page" not in html


def test_escapes_catalog_text():
    html = render_landing.render(TEMPLATE, CATALOG, URL)
    assert "&lt;b&gt;&amp;" in html and "<b>" not in html


def test_real_template_renders():
    template = (ROOT / "landing" / "index.html").read_text()
    catalog = yaml.safe_load((ROOT / "portal" / "catalog.yaml").read_text())
    html = render_landing.render(template, catalog, URL)
    assert '<meta name="viewport"' in html and 'src="architecture.svg"' in html
    assert "localhost" not in html and "host.docker.internal" not in html


def test_build_writes_page_and_diagram(tmp_path):
    render_landing.build(tmp_path, URL)
    assert "dp-portal.example.com" in (tmp_path / "index.html").read_text()
    assert (tmp_path / "architecture.svg").read_bytes() == (ROOT / "docs" / "architecture.svg").read_bytes()
