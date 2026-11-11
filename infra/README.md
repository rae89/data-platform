# infra

`terraform apply` here creates one EC2 spot instance (t4g.large, 8 GB, about $24/month)
running the stack. The AWS security group opens no ports. Two ways in:

- **Tailscale only (default, no domain).** People sign in to your tailnet with Google
  and open `http://data-platform-prod:<port>`. Each person installs the Tailscale app;
  invite them from the Tailscale admin console.
- **Public URLs (set `domain`).** Every service at `https://<name>.<domain>` behind
  Google sign-in (Cloudflare Access, free up to 50 users), no app needed. cloudflared on
  the instance dials out to Cloudflare. Needs a new domain (step 1 below).

## Tailscale-only deploy (about 20 minutes)

1. Store a Tailscale auth key in SSM:
   `aws ssm put-parameter --name /data-platform/tailscale-auth-key --type SecureString --value "$(op read op://Personal/data-platform-tailscale/credential)"`
2. `terraform -chdir=infra init`, then `terraform -chdir=infra apply`.
3. Wait about 3 minutes, then `ssh ubuntu@data-platform-prod` (Tailscale SSH).
4. Clone the repo, copy `.env.example` to `.env`, fill in the secrets and set
   `HOMEPAGE_ALLOWED_HOSTS=localhost:3002,data-platform-prod:3002`.
5. Run `PLATFORM_ENV=prod just up`. Open the portal at http://data-platform-prod:3002.

## Adding public URLs: one-time setup (about 30 minutes)

1. **Cloudflare:** register a new domain for the platform in Cloudflare (Domain
   Registration → Register Domains, about $10 to $12/year for a `.com`); its DNS is on
   Cloudflare from the start. Don't reuse the domains in Route 53: they carry live
   sites, and moving their DNS risks breaking them. Then open Zero Trust once to pick
   a team name (`<team>.cloudflareaccess.com`), and create an API token with Account: Cloudflare
   Tunnel Edit, Account: Access: Apps and Policies Edit, Account: Access: Organizations,
   Identity Providers, and Groups Edit, and Zone: DNS Edit.
2. **Google:** in Google Cloud Console → APIs & Services → Credentials, create an OAuth
   client ("Web application") with redirect URI
   `https://<team>.cloudflareaccess.com/cdn-cgi/access/callback`.
3. **Variables:** create `infra/terraform.tfvars` (gitignored):

   ```hcl
   domain                = "example.com"
   cloudflare_account_id = "..."
   allowed_emails        = ["you@gmail.com"]
   google_client_id      = "....apps.googleusercontent.com"
   ```

## Adding public URLs: deploy (about 20 minutes)

1. Apply, with secrets from 1Password:
   `CLOUDFLARE_API_TOKEN=$(op read ...) TF_VAR_google_client_secret=$(op read ...) terraform -chdir=infra apply`
2. On an instance created without a domain, cloud-init didn't install cloudflared. Over
   `ssh ubuntu@data-platform-prod`, run the `cloudflared` block at the end of
   `infra/user_data.sh` with `sudo` (replace the template variables). A new instance
   does this at boot.
3. Add the "Public deploy" lines to `.env` (`HOMEPAGE_ALLOWED_HOSTS`,
   `PORTAL_PUBLIC_URL`), then run `just up`.
4. Run `PORTAL_PUBLIC_URL=https://{name}.example.com just portal`.
5. Open `https://portal.example.com` and sign in with Google. `terraform -chdir=infra output urls`
   lists every URL.

No shell over Tailscale? Run the `ssm_shell` output command and check
`/var/log/cloud-init-output.log`.

## Adding a service

Add it to `local.services` in `public.tf` (subdomain → port) and set `public:` to the
same name in `portal/catalog.yaml`, then `terraform apply` and `just portal`.

## Choices

- **Cloudflare Access in front of everything.** Dagster, the portal and the Victoria
  UIs have no login, so the only way in is through Access. Don't open ports in the
  security group: that would bypass it.
- **Inside, apps trust everyone who got through.** Grafana keeps anonymous Admin and
  Superset its own `admin` login; the services don't check the Access token.
- **Spot, persistent, stop on interruption.** The disk survives and the instance comes
  back when capacity returns. Set `spot = false` for on-demand (about $56/month).
- **ARM by default.** For x86, set `instance_type = "t3a.large"`; the AMI follows.
- **Local state** (`infra/terraform.tfstate`, gitignored) holds the tunnel token and the
  Google client secret. Keep it private; move it to an encrypted S3 backend before
  anyone else runs this. `terraform destroy` deletes the disk and its data.
