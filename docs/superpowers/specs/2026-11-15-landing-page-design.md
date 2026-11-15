# Public landing page on Cloudflare Pages

Approved 2026-11-15. Small change, about 2 to 3 hours.

## Why

Anyone can open a public page that explains the data platform. Only emails in
`allowed_emails` get past its Sign in button. Today a visitor sees only a
Cloudflare/Google login screen, with nothing about what's behind it.

## Goals

- A static page anyone can load without signing in: what the platform is, the
  architecture diagram, what's inside (Dagster, Grafana, Superset, ...), and a Sign in
  button.
- Sign in opens the portal hostname. Cloudflare Access → Google → `allowed_emails`
  works exactly as it does now.

## Non-goals

- Visitor (non-allowlisted) access: issue #19 stays separate.
- Live data or health on the public page.

## Anti-goals

- Nothing on the server becomes reachable without Access. Every server hostname
  stays in the one Access application in `infra/public.tf`.

## Approaches

| Approach | Trade-off | Picked |
|---|---|---|
| Cloudflare Pages | $0, no upkeep, up when the spot instance is down, server untouched | **Yes**: cheapest and lowest maintenance |
| Small web server on the instance (Caddy) | Down whenever the instance is; first unprotected hostname on the server | No |
| S3 + Cloudflare proxy | Public bucket, HTTP hop, per-hostname SSL exception | No |
| S3 + CloudFront | About $1/month, ~6 resources, cross-provider certificate validation | No |
| Make the Homepage portal public | Leaks live health, metrics and links; Homepage can't hide parts | Ruled out |

## Design

1. **Page:** `landing/index.html`, plain HTML and CSS, no build step. Reuses
   `docs/architecture.svg` (copied in at deploy time, not hand-edited).
2. **Hosting (OpenTofu, `infra/landing.tf`):** `cloudflare_pages_project`;
   `cloudflare_pages_domain` and a proxied `cloudflare_dns_record` CNAME to
   `<project>.pages.dev` on the zone apex, created only when `domain` is set. Until
   then the page is at `<project>.pages.dev`.
3. **Deploy:** a GitHub Actions job runs `wrangler pages deploy` on merge to `main`
   when `landing/` (or the diagram) changes. A Cloudflare API token, scoped to Pages
   edit, goes in a GitHub secret; documented in `infra/README.md` and `.env.example`.
4. **Sign in link:** points at the portal hostname
   (`${hostname_prefix}portal.${domain}`), so Access handles login.
5. **Docs:** README section; `docs/diagram/architecture.mjs` draws the landing page in
   front of Access, then `just diagram`; `portal/catalog.yaml` unchanged (the page
   isn't a server service).

## Left to the builder

- The page text: draft from `README.md` for the owner to edit.
- Styling: simple, matches the README's tone; works at phone width.
