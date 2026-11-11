# infra

`terraform apply` here creates one EC2 spot instance (t4g.large, 8 GB, about $24/month)
with Docker, `just` and Tailscale installed. It opens no ports: you reach the services
over your tailnet. Deploying the repo onto it is still manual (steps 4 and 5).

## Deploy (about 30 minutes)

1. Store a Tailscale auth key (Tailscale admin → Settings → Keys) in SSM, outside
   Terraform so it stays out of state:
   `aws ssm put-parameter --name /data-platform/tailscale-auth-key --type SecureString --value "$(op read op://Personal/data-platform-tailscale/credential)"`
2. `terraform -chdir=infra init`, then `terraform -chdir=infra apply`.
3. Wait about 3 minutes for `data-platform-prod` to show up in your tailnet, then
   `ssh ubuntu@data-platform-prod` (Tailscale SSH).
4. Clone the repo onto it and fill in `.env` from `.env.example`.
5. Run `PLATFORM_ENV=prod just up`. Open the portal at http://data-platform-prod:3002.

No shell over Tailscale? Run the `ssm_shell` output command and check
`/var/log/cloud-init-output.log`.

## Choices

- **Spot, persistent, stop on interruption.** The disk survives and the instance comes
  back when capacity returns. Set `spot = false` for on-demand (about $56/month).
- **ARM by default.** Every service has an arm64 image except Lightdash (parked). For
  x86, set `instance_type = "t3a.large"`; the AMI follows the architecture.
- **Default VPC with a public IP**, so outbound traffic needs no NAT gateway (about
  $32/month). The security group allows no inbound traffic.
- **Local state** (`infra/terraform.tfstate`, gitignored). Move it to S3 before anyone
  else runs this.
- `terraform destroy` deletes the disk, including the warehouse and Dagster history.
