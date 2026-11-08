import importlib.util
from pathlib import Path

import yaml

PORTAL = Path(__file__).parents[1] / "portal"
spec = importlib.util.spec_from_file_location("render_homepage", PORTAL / "render_homepage.py")
render_homepage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_homepage)

catalog = yaml.safe_load((PORTAL / "catalog.yaml").read_text())


def test_generated_config_matches_catalog():
    # Fails when catalog.yaml was edited without running `just portal`.
    assert render_homepage.SERVICES.read_text() == render_homepage.render(catalog)


def test_render_groups_services_and_maps_fields():
    rendered = yaml.safe_load(
        render_homepage.render(
            {
                "components": [
                    {"name": "A", "group": "G1", "description": "a", "url": "http://a"},
                    {
                        "name": "B",
                        "group": "G2",
                        "description": "b",
                        "url": "http://b",
                        "health": "http://b/health",
                        "icon": "b.png",
                        "homepage": {"widget": {"type": "customapi"}},
                    },
                    {"name": "C", "group": "G1", "description": "c", "url": "http://c"},
                ]
            }
        )
    )
    assert rendered == [
        {"G1": [{"A": {"href": "http://a", "description": "a"}}, {"C": {"href": "http://c", "description": "c"}}]},
        {
            "G2": [
                {
                    "B": {
                        "href": "http://b",
                        "description": "b",
                        "icon": "b.png",
                        "siteMonitor": "http://b/health",
                        "widget": {"type": "customapi"},
                    }
                }
            ]
        },
    ]


def test_catalog_is_complete():
    entries = catalog["components"] + catalog.get("feeds", [])
    # Homepage identifies a tile by group + name (e.g. its widget proxy URL).
    keys = [(e["group"], e["name"]) for e in entries]
    assert len(keys) == len(set(keys)), "names must be unique within a group"
    for e in entries:
        assert {"name", "group", "description", "url"} <= e.keys(), e["name"]
    for f in catalog.get("feeds", []):
        assert "type" in f.get("source", {}), f["name"]
    # Every group needs a layout entry, or Homepage falls back to its default layout.
    layout = yaml.safe_load((PORTAL / "homepage" / "settings.yaml").read_text())["layout"]
    assert {e["group"] for e in entries} <= layout.keys()


def test_feeds_render_as_widgets():
    rendered = yaml.safe_load(
        render_homepage.render(
            {
                "components": [],
                "feeds": [
                    {
                        "name": "PRs",
                        "group": "Updates",
                        "description": "merged",
                        "url": "http://gh",
                        "source": {"type": "github-merged-prs", "repo": "o/r"},
                    },
                    {
                        "name": "Tool",
                        "group": "Upstream",
                        "description": "releases",
                        "url": "http://t",
                        "icon": "t.png",
                        "source": {"type": "atom", "url": "http://t/releases.atom"},
                    },
                ],
            }
        )
    )
    prs = rendered[0]["Updates"][0]["PRs"]["widget"]
    assert "repo:o/r+is:pr+is:merged" in prs["url"]
    # The token is never rendered, only Homepage's placeholder for the env var.
    assert prs["headers"]["Authorization"] == "Bearer {{HOMEPAGE_VAR_GITHUB_TOKEN}}"
    assert prs["mappings"]["target"] == "{html_url}"
    assert prs["headers"]["User-Agent"]  # GitHub returns 403 without one

    tool = rendered[1]["Upstream"][0]["Tool"]
    assert tool["icon"] == "t.png"
    assert tool["widget"] == {"type": "feed", "url": "http://t/releases.atom", "maxItems": 5, "images": False}


def test_unknown_feed_type_fails_loudly():
    import pytest

    with pytest.raises(ValueError, match="Unknown feed source type: rss2"):
        render_homepage.feed_widget({"type": "rss2"})

