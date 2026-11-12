# infra

`tofu apply` ([OpenTofu](https://opentofu.org), `brew install opentofu`) here creates
one EC2 spot instance (t4g.large, 8 GB, about $24/month) running the stack. The AWS
security group opens no ports. Ways in:

- **SSM Session Manager (default, nothing to set up).** A shell, and port forwarding
  to `localhost`, signed in with your AWS credentials. Only for people with AWS access.
- **Tailscale (optional, set `tailscale_auth_key_parameter`).** Anyone you invite signs
  in to your tailnet with Google and opens `http://data-platform-prod:<port>`.

## Deploy (about 20 minutes)

1. Install the AWS CLI's Session Manager plugin: `brew install --cask session-manager-plugin`.
2. `tofu -chdir=infra init`, then `tofu -chdir=infra apply`.
3. Wait about 3 minutes, then open a shell with the `ssm_shell` output command and run
   `sudo -iu ubuntu` (that user can run Docker).
4. Clone the repo, `git clone https://github.com/rae89/data-platform.git`, and copy
   `.env.example` to `.env`, filling in the secrets and `PLATFORM_ENV=prod`.
5. Run `just up`. The first build takes about 10 to 15 minutes.

To open a service, run the `port_forward` output command on your laptop and keep it
running: http://localhost:3002 is the portal. For Dagster, change both port numbers to
3000; Grafana 3001, Superset 8088. Portal links to other services work for the ports
you forward.

Boot problems: `/var/log/cloud-init-output.log` on the instance.

## Adding Tailscale

1. Store an auth key in SSM:
   `aws ssm put-parameter --name /data-platform/tailscale-auth-key --type SecureString --value "$(op read op://Personal/data-platform-tailscale/credential)"`
2. Set `tailscale_auth_key_parameter = "/data-platform/tailscale-auth-key"` in
   `infra/terraform.tfvars` and run `tofu -chdir=infra apply`.
3. On an existing instance, cloud-init won't rerun: in an SSM shell, run the Tailscale
   block of `infra/user_data.sh` with `sudo` (replace the template variables).
4. Add `data-platform-prod:3002` to `HOMEPAGE_ALLOWED_HOSTS` in `.env`, then `just up`.

## Choices

- **Spot, persistent, stop on interruption.** The disk survives and the instance comes
  back when capacity returns. Set `spot = false` for on-demand (about $56/month).
- **ARM by default.** For x86, set `instance_type = "t3a.large"`; the AMI follows.
- **Local state** (`infra/terraform.tfstate`, gitignored). Keep it private; move it to
  an encrypted S3 backend before anyone else runs this. `tofu destroy` deletes the disk
  and its data.
