# Public access with Google SSO through Cloudflare Access. cloudflared on the instance
# opens an outbound tunnel, so the security group stays closed. Every hostname sits
# behind one Access application: nobody reaches a service without signing in.

locals {
  # Subdomain → port on the instance. Keep in sync with `public:` in portal/catalog.yaml.
  services = {
    portal          = 3002
    dagster         = 3000
    grafana         = 3001
    superset        = 8088
    victoriametrics = 8428
    victorialogs    = 9428
    vmalert         = 8880
  }
  # One level under the zone: Cloudflare's free certificate doesn't cover a.b.example.com.
  hostnames = { for name, port in local.services : name => "${var.hostname_prefix}${name}.${var.domain}" }
}

data "cloudflare_zone" "this" {
  filter = { name = var.domain }
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "this" {
  account_id = var.cloudflare_account_id
  name       = "data-platform-${var.env}"
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "this" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.this.id
  config = {
    ingress = concat(
      [for name, port in local.services : { hostname = local.hostnames[name], service = "http://localhost:${port}" }],
      [{ service = "http_status:404" }], # anything else
    )
  }
}

resource "cloudflare_dns_record" "this" {
  for_each = local.hostnames
  zone_id  = data.cloudflare_zone.this.id
  name     = each.value
  type     = "CNAME"
  content  = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied  = true
  ttl      = 1 # automatic
}

data "cloudflare_zero_trust_tunnel_cloudflared_token" "this" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.this.id
}

# The instance reads the tunnel token at boot, like the Tailscale key. It is also in
# Terraform state, which is why state must stay private.
resource "aws_ssm_parameter" "tunnel_token" {
  name  = "/data-platform/${var.env}/cloudflare-tunnel-token"
  type  = "SecureString"
  value = data.cloudflare_zero_trust_tunnel_cloudflared_token.this.token
}

resource "cloudflare_zero_trust_access_identity_provider" "google" {
  account_id = var.cloudflare_account_id
  name       = "Google"
  type       = "google"
  config = {
    client_id     = var.google_client_id
    client_secret = var.google_client_secret
  }
}

resource "cloudflare_zero_trust_access_policy" "allowed" {
  account_id = var.cloudflare_account_id
  name       = "data-platform-${var.env} users"
  decision   = "allow"
  include    = [for email in var.allowed_emails : { email = { email = email } }]
}

resource "cloudflare_zero_trust_access_application" "this" {
  account_id                = var.cloudflare_account_id
  name                      = "data-platform-${var.env}"
  type                      = "self_hosted"
  destinations              = [for host in values(local.hostnames) : { type = "public", uri = host }]
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.google.id]
  auto_redirect_to_identity = true # straight to Google, no Cloudflare chooser page
  session_duration          = "24h"
  policies                  = [{ id = cloudflare_zero_trust_access_policy.allowed.id, precedence = 1 }]
}
