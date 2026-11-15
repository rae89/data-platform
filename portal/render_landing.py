"""Renders the public landing page (landing/index.html) into landing/dist. Run it with `just landing`."""

import html
import os
import shutil
from pathlib import Path
from string import Template

import yaml

ROOT = Path(__file__).parents[1]
CATALOG = ROOT / "portal" / "catalog.yaml"
TEMPLATE = ROOT / "landing" / "index.html"
DIAGRAM = ROOT / "docs" / "architecture.svg"
DIST = ROOT / "landing" / "dist"


def sign_in_url(public_url: str | None) -> str:
    """The portal's public hostname; Cloudflare Access signs people in there."""
    if not public_url or "{name}" not in public_url:
        raise ValueError("PORTAL_PUBLIC_URL must look like https://{name}.example.com")
    return public_url.format(name="portal") + "/"


def render(template: str, catalog: dict, public_url: str | None) -> str:
    # Only components with a public hostname: visitors can never reach the others.
    items = "\n".join(
        f"<li><strong>{html.escape(c['name'])}</strong> {html.escape(c['description'])}</li>"
        for c in catalog["components"]
        if "public" in c
    )
    return Template(template).substitute(sign_in_url=html.escape(sign_in_url(public_url)), components=items)


def build(out_dir: Path, public_url: str | None) -> None:
    page = render(TEMPLATE.read_text(), yaml.safe_load(CATALOG.read_text()), public_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page)
    shutil.copyfile(DIAGRAM, out_dir / "architecture.svg")


if __name__ == "__main__":
    build(DIST, os.environ.get("PORTAL_PUBLIC_URL"))
    print(f"wrote {DIST.relative_to(ROOT)}")
