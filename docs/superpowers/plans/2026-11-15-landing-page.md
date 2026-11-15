# Public Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public static page on Cloudflare Pages explaining the platform, whose Sign in button leads to the Access-protected portal.

**Architecture:** `landing/index.html` is a `string.Template`. `portal/render_landing.py` fills it from `portal/catalog.yaml` (only `public:` components) and `PORTAL_PUBLIC_URL`, and writes `landing/dist/` (already gitignored via `dist/`). OpenTofu (`infra/landing.tf`) creates the Pages project, apex custom domain and DNS. `.github/workflows/landing.yml` renders and runs `wrangler pages deploy` on merge to `main`.

**Tech Stack:** Python 3.12 stdlib + PyYAML (already a dependency), OpenTofu with `cloudflare/cloudflare ~> 5.28`, `cloudflare/wrangler-action@v3`, d3 diagram script.

**Spec:** `docs/superpowers/specs/2026-11-15-landing-page-design.md`

## Global Constraints

- Only emails in `allowed_emails` get past Sign in; no server hostname leaves the Access application in `infra/public.tf`.
- The page is static: no live data, no health, no internal URLs (`localhost`, `host.docker.internal`).
- Cloudflare resources exist only when `var.domain` is set (`local.public`), like `public.tf`.
- No new dependencies. No secrets in the repo: the Cloudflare token is a GitHub secret.
- Docs follow the i-have-adhd style (AGENTS.md "Writing PRs and docs").
- `PORTAL_PUBLIC_URL` keeps its existing format: `https://<prefix>{name}.<domain>`.

## Review Focus

1. `PORTAL_PUBLIC_URL` unset or without `{name}` → render fails loudly, never a page with a broken Sign in link. (Task 1 test `test_sign_in_url_rejects_missing_or_bad_value`.)
2. Catalog text containing `<`, `&` or quotes → escaped, not injected into the page. (Task 1 test `test_escapes_catalog_text`.)
3. A component without `public:` (dlt dashboard, local-only) → not listed, since visitors could never reach it. (Task 1 test `test_lists_only_public_components`.)
4. Phone-width visitor → readable without horizontal scroll. (Task 1 test `test_real_template_renders` checks the viewport meta; Task 1 Step 6 checks at 375px by eye.)
5. Deploy before `tofu apply` or before repo variables are set → the job is skipped, not failed. (Task 3 `if:` condition.)

---

### Task 1: Page template and renderer

**Files:**
- Create: `landing/index.html`
- Create: `portal/render_landing.py`
- Modify: `justfile` (new `landing` recipe after `portal`)
- Test: `tests/test_landing.py`

**Interfaces:**
- Produces: `sign_in_url(public_url: str | None) -> str`; `render(template: str, catalog: dict, public_url: str | None) -> str`; `build(out_dir: Path, public_url: str | None) -> None` (writes `out_dir/index.html` and copies `docs/architecture.svg` to `out_dir/architecture.svg`). CLI: `uv run python portal/render_landing.py` reads `PORTAL_PUBLIC_URL`, builds into `landing/dist`.
- Template placeholders (`string.Template`, filled with `substitute`, so a missing one raises): `$sign_in_url`, `$components`.

- [ ] **Step 1: Write the failing tests** in `tests/test_landing.py` (import the module the way `tests/test_portal.py` imports `render_homepage`):

```python
URL = "https://dp-{name}.example.com"
CATALOG = {"components": [
    {"name": "Dagster", "group": "Orchestration", "description": "Runs <b>& assets", "url": "http://localhost:3000", "public": "dagster"},
    {"name": "dlt dashboard", "group": "Orchestration", "description": "local", "url": "http://localhost:2718"},
]}
TEMPLATE = "<a href=\"$sign_in_url\">Sign in</a><ul>$components</ul>"

def test_sign_in_points_at_public_portal():
    assert 'href="https://dp-portal.example.com/"' in render(TEMPLATE, CATALOG, URL)

def test_sign_in_url_rejects_missing_or_bad_value():
    for bad in (None, "", "https://example.com"):
        with pytest.raises(ValueError):
            sign_in_url(bad)

def test_lists_only_public_components():
    html = render(TEMPLATE, CATALOG, URL)
    assert "Dagster" in html and "dlt dashboard" not in html

def test_escapes_catalog_text():
    html = render(TEMPLATE, CATALOG, URL)
    assert "&lt;b&gt;&amp;" in html and "<b>" not in html

def test_real_template_renders():
    html = render(Path("landing/index.html").read_text(), yaml.safe_load(Path("portal/catalog.yaml").read_text()), URL)
    assert '<meta name="viewport"' in html and 'src="architecture.svg"' in html
    assert "localhost" not in html and "host.docker.internal" not in html

def test_build_writes_page_and_diagram(tmp_path):
    build(tmp_path, URL)
    assert (tmp_path / "index.html").read_text().count("dp-portal.example.com") >= 1
    assert (tmp_path / "architecture.svg").read_bytes() == Path("docs/architecture.svg").read_bytes()
```

- [ ] **Step 2: Run** `just test tests/test_landing.py`. Expected: FAIL (module not found).

- [ ] **Step 3: Implement `portal/render_landing.py`.** `sign_in_url` returns `public_url.format(name="portal") + "/"` and raises `ValueError` when the value is empty or has no `{name}`. `render` lists each component with `public:` as `<li><strong>{name}</strong> {description}</li>` (both through `html.escape`), in catalog order. Docstring and `__main__` block follow `render_homepage.py`; print `wrote landing/dist`.

- [ ] **Step 4: Write `landing/index.html`.** One self-contained page with inline CSS: `<meta name="viewport" content="width=device-width, initial-scale=1">`, a title and one-line pitch, `<img src="architecture.svg" alt="...">` (reuse the README's alt text), "What's inside" `<ul>$components</ul>`, and a Sign in button (`<a href="$sign_in_url">`) at the top and the bottom. Copy comes from `README.md`'s first lines; a note in the page source says it's a draft for the owner to edit. Max content width about 720px, 16px side padding, image `max-width: 100%`. Light and dark via `prefers-color-scheme`.

- [ ] **Step 5: Add the recipe** to `justfile` after `portal`:

```
# Public landing page (Cloudflare Pages) into landing/dist; needs PORTAL_PUBLIC_URL
landing:
    uv run python portal/render_landing.py
```

- [ ] **Step 6: Run** `just test tests/test_landing.py` (expected: 6 passed), then `PORTAL_PUBLIC_URL='https://{name}.example.com' just landing` and open `landing/dist/index.html`. Expected: the diagram shows, there's no horizontal scroll at 375px wide, and Sign in goes to `https://portal.example.com/`.

- [ ] **Step 7: Commit** `landing/index.html portal/render_landing.py justfile tests/test_landing.py` with the message "Add the public landing page and its renderer".

### Task 2: Pages project, domain and DNS in OpenTofu

**Files:**
- Create: `infra/landing.tf`
- Modify: `infra/outputs.tf` (new `landing` output)
- Modify: `infra/README.md` (new "Public landing page" section)

**Interfaces:**
- Consumes: `local.public`, `var.domain`, `var.cloudflare_account_id`, `var.env`, `data.cloudflare_zone.this[0].id` (all from `public.tf` / `variables.tf`).
- Produces: output `landing = { project = <name>, url = "https://<domain>", pages_dev = "https://<subdomain>" }`, or `null` when `local.public` is false. Task 3 reads `project` as repo variable `CF_PAGES_PROJECT`.

- [ ] **Step 1: Write `infra/landing.tf`** with three resources, each `count = local.public ? 1 : 0`:
  - `cloudflare_pages_project.landing`: `name = "data-platform-${var.env}"`, `production_branch = "main"`, no `source` block (direct upload).
  - `cloudflare_pages_domain.landing`: `name = var.domain` on that project.
  - `cloudflare_dns_record.landing`: apex `CNAME` to the project's `subdomain` (`<name>.pages.dev`), `proxied = true`, `ttl = 1`.
  - Header comment: public on purpose, static, no data; every server hostname stays behind Access in `public.tf`.

- [ ] **Step 2: Add the `landing` output** to `infra/outputs.tf` (shape above).

- [ ] **Step 3: Run** `tofu -chdir=infra fmt -check && tofu -chdir=infra init -backend=false -input=false >/dev/null && tofu -chdir=infra validate`. Expected: `Success! The configuration is valid.`

- [ ] **Step 4: Document it in `infra/README.md`.** Cover:
  - that `tofu apply` creates the project at the apex domain;
  - the GitHub settings Task 3 needs, as a numbered list (the secret `CLOUDFLARE_PAGES_TOKEN` with the "Cloudflare Pages: Edit" permission, and the variables `CLOUDFLARE_ACCOUNT_ID`, `CF_PAGES_PROJECT` from `tofu output landing` and `PORTAL_PUBLIC_URL`);
  - how to preview locally with `just landing`.

- [ ] **Step 5: Commit** `infra/landing.tf infra/outputs.tf infra/README.md` with the message "Host the landing page on Cloudflare Pages (OpenTofu)".

### Task 3: Deploy on merge to main

**Files:**
- Create: `.github/workflows/landing.yml`

**Interfaces:**
- Consumes: `just landing` / `portal/render_landing.py` (Task 1); repo variables `CF_PAGES_PROJECT`, `CLOUDFLARE_ACCOUNT_ID` and `PORTAL_PUBLIC_URL`, and the secret `CLOUDFLARE_PAGES_TOKEN` (Task 2 README).

- [ ] **Step 1: Write the workflow.**
  - Triggers: `push` to `main` with paths `landing/**`, `portal/catalog.yaml`, `portal/render_landing.py`, `docs/architecture.svg` and `.github/workflows/landing.yml`; plus `workflow_dispatch`.
  - `permissions: contents: read`, and `concurrency: landing` with `cancel-in-progress: false`.
  - One job with `if: vars.CF_PAGES_PROJECT != ''`, so it's skipped until set up.
  - Steps:
    1. `actions/checkout@v4`
    2. `astral-sh/setup-uv@v6`
    3. `uv run python portal/render_landing.py`, with `PORTAL_PUBLIC_URL: ${{ vars.PORTAL_PUBLIC_URL }}`
    4. `cloudflare/wrangler-action@v3`, with `apiToken: ${{ secrets.CLOUDFLARE_PAGES_TOKEN }}`, `accountId: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}` and `command: pages deploy landing/dist --project-name=${{ vars.CF_PAGES_PROJECT }} --branch=main`

- [ ] **Step 2: Run** `actionlint .github/workflows/landing.yml` (or `uvx actionlint-py` if it isn't installed). Expected: no output, exit 0.

- [ ] **Step 3: Commit** `.github/workflows/landing.yml` with the message "Deploy the landing page to Cloudflare Pages on merge to main".

### Task 4: Diagram and project docs

**Files:**
- Modify: `docs/diagram/architecture.mjs` (node + edge), then regenerate `docs/architecture.svg`
- Modify: `README.md` (alt text on line 5; new "Landing page" section before "## Portal")
- Modify: `AGENTS.md` (Layout: `landing/`, `portal/render_landing.py`; the "Public access" rule now notes the one public static page)

- [ ] **Step 1: Add the node and edge** to `architecture.mjs`:
  - node `{ id: "landing", x: 930, y: 460, kind: "portal", title: "Landing page", sub: "Cloudflare Pages, public" }`
  - edge `{ from: "landing", to: "portal", side: "v", label: "Sign in (Access)" }`

  If either overlaps something, move it to the nearest clear spot.

- [ ] **Step 2: Run** `just diagram` and open `docs/architecture.svg`. Expected: the landing node sits below the portal, its label doesn't overlap anything, and the file is regenerated.

- [ ] **Step 3: Update the docs.**
  - README section: what the page is, that only `allowed_emails` get past Sign in, and how to preview it (`PORTAL_PUBLIC_URL=... just landing`). Link `infra/README.md` for setup.
  - Add the landing page to the README alt text.
  - AGENTS.md: the Layout lines, and the Public access rule: "the landing page (`landing/`, Cloudflare Pages) is the only public page: static, no data, no internal links".

- [ ] **Step 4: Run** `just ci`. Expected: every step passes and coverage stays ≥ 99%.

- [ ] **Step 5: Commit** `docs/diagram/architecture.mjs docs/architecture.svg README.md AGENTS.md` with the message "Document the landing page and draw it on the architecture diagram".
