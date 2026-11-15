# Public landing page on Cloudflare Pages, at the zone apex. Public on purpose: it's
# static, holds no data and links only to the portal, whose hostname (like every server
# hostname) stays behind Access in public.tf. Files are uploaded by
# .github/workflows/landing.yml, not by OpenTofu.

resource "cloudflare_pages_project" "landing" {
  count             = local.public ? 1 : 0
  account_id        = var.cloudflare_account_id
  name              = "data-platform-${var.env}"
  production_branch = "main"
}

resource "cloudflare_pages_domain" "landing" {
  count        = local.public ? 1 : 0
  account_id   = var.cloudflare_account_id
  project_name = cloudflare_pages_project.landing[0].name
  name         = var.domain
}

# Pages doesn't create the record for API-added domains.
resource "cloudflare_dns_record" "landing" {
  count   = local.public ? 1 : 0
  zone_id = data.cloudflare_zone.this[0].id
  name    = var.domain
  type    = "CNAME"
  content = cloudflare_pages_project.landing[0].subdomain
  proxied = true
  ttl     = 1 # automatic
}
