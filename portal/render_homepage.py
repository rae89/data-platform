"""Renders portal/catalog.yaml into Homepage's services.yaml. Run it with `just portal`."""

import os
from pathlib import Path
from urllib.parse import urlsplit

import yaml

PORTAL = Path(__file__).parent
CATALOG = PORTAL / "catalog.yaml"
SERVICES = PORTAL / "homepage" / "services.yaml"
HEADER = "# Generated from portal/catalog.yaml by `just portal`. Don't edit by hand.\n"
FEED_ITEMS = 5


def feed_widget(source: dict) -> dict:
    """Homepage widget for a catalog feed source."""
    if source["type"] == "atom":
        return {"type": "feed", "url": source["url"], "maxItems": FEED_ITEMS, "images": False}
    if source["type"] == "github-merged-prs":
        query = f"repo:{source['repo']}+is:pr+is:merged"
        return {
            "type": "customapi",
            "url": f"https://api.github.com/search/issues?q={query}&sort=created&order=desc&per_page={FEED_ITEMS}",
            # Homepage replaces this with the container's HOMEPAGE_VAR_GITHUB_TOKEN.
            "headers": {
                "Authorization": "Bearer {{HOMEPAGE_VAR_GITHUB_TOKEN}}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "data-platform-portal",  # GitHub rejects requests without one
            },
            "refreshInterval": 300_000,  # 5 min, well under GitHub's rate limit
            "display": "dynamic-list",
            "mappings": {
                "items": "items",
                "name": "title",
                "label": "closed_at",
                "format": "relativeDate",
                "limit": FEED_ITEMS,
                "target": "{html_url}",
            },
        }
    raise ValueError(f"Unknown feed source type: {source['type']}")


def base_service(entry: dict, public_url: str | None = None) -> dict:
    """Fields every catalog entry (component or feed) maps the same way."""
    href = entry["url"]
    if public_url and "public" in entry:
        # Public deploy (infra/public.tf): same path on the service's public hostname.
        parts = urlsplit(href)
        href = public_url.format(name=entry["public"]) + parts.path + (f"?{parts.query}" if parts.query else "")
    service = {"href": href, "description": entry["description"]}
    if "icon" in entry:
        service["icon"] = entry["icon"]
    return service


def render(catalog: dict, public_url: str | None = None) -> str:
    groups: dict[str, list] = {}  # keeps catalog order
    for c in catalog["components"]:
        service = base_service(c, public_url)
        if "health" in c:
            service["siteMonitor"] = c["health"]
        service.update(c.get("homepage", {}))
        groups.setdefault(c["group"], []).append({c["name"]: service})
    for f in catalog.get("feeds", []):
        service = base_service(f) | {"widget": feed_widget(f["source"])}
        groups.setdefault(f["group"], []).append({f["name"]: service})
    body = yaml.safe_dump([{g: s} for g, s in groups.items()], sort_keys=False, allow_unicode=True)
    return HEADER + body


if __name__ == "__main__":
    # e.g. https://{name}.example.com: links point at the public hostnames, not localhost.
    SERVICES.write_text(render(yaml.safe_load(CATALOG.read_text()), os.environ.get("PORTAL_PUBLIC_URL")))
    print(f"wrote {SERVICES.relative_to(PORTAL.parent)}")
