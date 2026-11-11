#!/bin/bash
# First boot only (cloud-init). Installs Docker, just, Tailscale and cloudflared, then
# joins the tailnet and starts the Cloudflare tunnel. Deploying the repo is a manual
# step for now (infra/README.md).
set -euxo pipefail

apt-get update
apt-get install -y docker.io docker-compose-v2 just git
systemctl enable --now docker
usermod -aG docker ubuntu

snap install aws-cli --classic
curl -fsSL https://tailscale.com/install.sh | sh

key=$(aws ssm get-parameter --region ${region} --name "${tailscale_key_param}" \
  --with-decryption --query Parameter.Value --output text)
# --ssh: Tailscale SSH, so no SSH port or key pair is needed.
tailscale up --auth-key="$key" --hostname=${tailscale_hostname} --ssh

# cloudflared from Cloudflare's signed apt repo (updates with apt upgrade).
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  > /etc/apt/sources.list.d/cloudflared.list
apt-get update
apt-get install -y cloudflared
token=$(aws ssm get-parameter --region ${region} --name "${tunnel_token_param}" \
  --with-decryption --query Parameter.Value --output text)
cloudflared service install "$token" # systemd service; routes come from public.tf
