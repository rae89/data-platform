# infra

`tofu apply` ([OpenTofu](https://opentofu.org), `brew install opentofu`) here creates
one EC2 spot instance (t4g.large, 8 GB, about $24/month) running the stack. The AWS
security group opens no ports. Ways in:

- **SSM Session Manager (default, nothing to set up).** A shell, and port forwarding
  to `localhost`, signed in with your AWS credentials. Only for people with AWS access.
- **Public URLs (optional, set `domain`).** Every service at `https://<name>.<domain>`
  behind Google sign-in (Cloudflare Access), in any browser. Needs a new domain.

## Deploy (about 20 minutes)

1. Install the AWS CLI's Session Manager plugin: `brew install --cask session-manager-plugin`.
2. `tofu -chdir=infra init`, then `tofu -chdir=infra apply`.
3. Wait about 3 minutes, then open a shell with the `ssm_shell` output command and run
   `sudo -iu ubuntu` (that user can run Docker).
4. Clone the repo, `git clone https://github.com/rae89/data-platform.git`, and copy
   `.env.example` to `.env`, filling in the secrets and `PLATFORM_ENV=prod`.
5. Run `just update`: it pulls the images CI built for the `main` commit
   (`ghcr.io/rae89/data-platform-*:sha-<commit>`) and starts everything, without
   building on the server.
6. Turn on deploys from CI: set the repository variables from step 3 of the next section.

To open a service, run the `port_forward` output command on your laptop and keep it
running: http://localhost:3002 is the portal. For Dagster, change both port numbers to
3000; Grafana 3001, Superset 8088. Portal links to other services work for the ports
you forward.

Boot problems: `/var/log/cloud-init-output.log` on the instance.

## Updates after a merge to `main` (automatic)

A merge to `main` updates the server about 1 minute after the "Images" workflow has
built both images, with no one logging in. Its `deploy` job signs in to AWS with GitHub
OIDC (no AWS keys in GitHub) and sends the server an SSM Run Command. On the server,
`infra/server/deploy.py`:

1. Runs `just update-pull <commit>`: fast-forward and pull the images built for that
   exact commit (tag `sha-<commit>`, retagged as `:main`).
2. Waits while a Dagster run is in progress (up to 60 minutes), so an update never
   kills a run. Still busy after that: the job fails with the new code checked out but
   not running; re-run it from the Actions tab.
3. Runs `docker compose up -d` right after the last check: restart what changed.

The AWS role may only run that one SSM document on this one instance, and only from
workflows on `main` of this repo. Its output is in the job log.

**Turn it on (about 10 minutes, once):**

1. `tofu -chdir=infra apply` creates the role, the document and the GitHub OIDC
   provider. If the account already has a GitHub OIDC provider, the apply fails:
   set `github_oidc_provider_arn` to its ARN in `terraform.tfvars` and apply again.
2. `tofu -chdir=infra output github_deploy` prints 4 values.
3. In GitHub: Settings → Secrets and variables → Actions → Variables, add each as a
   repository variable: `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `DEPLOY_INSTANCE_ID`,
   `DEPLOY_SSM_DOCUMENT`. They are identifiers, not secrets.
4. The next merge to `main` deploys. To deploy now, run the "Images" workflow on
   `main` from the Actions tab.

Until the variables are set, the job is skipped and `just update` on the server works
as before. To pause deploys, delete `AWS_DEPLOY_ROLE_ARN`. Local commits on the server
make the update fail (it only fast-forwards); the job log says so.

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

1. Apply, with the Cloudflare token and Google client secret from 1Password (items
   `data-platform-cloudflare` and `data-platform-google-oauth`, see `infra/.env.op`):
   `op run --env-file infra/.env.op -- tofu -chdir=infra apply`
2. On an instance created without a domain, cloud-init didn't install cloudflared. In an
   SSM shell, run the `cloudflared` block at the end of
   `infra/user_data.sh` with `sudo` (replace the template variables). A new instance
   does this at boot.
3. Add the "Public deploy" lines to `.env` (`HOMEPAGE_ALLOWED_HOSTS`,
   `PORTAL_PUBLIC_URL`, and for Superset sign-in through Access `CF_ACCESS_TEAM_DOMAIN`,
   `CF_ACCESS_AUD` from `tofu -chdir=infra output cf_access`, `SUPERSET_ADMIN_EMAILS`),
   then run `just up`. Superset then has no password login: reach it through Access.
4. Run `PORTAL_PUBLIC_URL=https://{name}.example.com just portal`.
5. Open `https://portal.example.com` and sign in with Google. `tofu -chdir=infra output urls`
   lists every URL.

## Public landing page (about 15 minutes)

With `domain` set, `tofu apply` also creates a Cloudflare Pages project (`landing.tf`)
serving `landing/` at `https://example.com`, the zone apex. It's the only public page:
static, no data, and its Sign in button opens the portal, where Access lets in only
`allowed_emails`. GitHub Actions (`.github/workflows/landing.yml`) publishes it on
merge to `main`; until the settings below exist, that job is skipped.

1. Give the Cloudflare token that `tofu` uses (1Password `data-platform-cloudflare`) the
   **Account → Cloudflare Pages → Edit** permission, then apply.
2. Create a second API token with only **Account → Cloudflare Pages → Edit** and add it
   to GitHub (Settings → Secrets and variables → Actions) as the secret
   `CLOUDFLARE_PAGES_TOKEN`.
3. Add 3 repository variables: `CF_PAGES_PROJECT` (`project` from
   `tofu -chdir=infra output landing`), `CLOUDFLARE_ACCOUNT_ID`, and `PORTAL_PUBLIC_URL`
   (the same value as in `.env`, e.g. `https://{name}.example.com`).
4. Run the "Landing page" workflow from the Actions tab, then open `https://example.com`.

Preview it locally: `PORTAL_PUBLIC_URL='https://{name}.example.com' just landing`, then
open `landing/dist/index.html`.

## Adding a service

Add it to `local.services` in `public.tf` (subdomain → port) and set `public:` to the
same name in `portal/catalog.yaml`, then `tofu apply` and `just portal`.

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
  anyone else runs this. `tofu destroy` deletes the disk and its data.
