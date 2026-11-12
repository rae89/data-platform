#!/bin/bash
# First boot only (cloud-init). Installs Docker and just; optionally joins Tailscale
# and starts the Cloudflare tunnel. Deploying the repo is a manual step for now
# (infra/README.md).
set -euxo pipefail

apt-get update
apt-get install -y docker.io docker-compose-v2 just git
systemctl enable --now docker
usermod -aG docker ubuntu

# 4 GB swap: an image build next to the running stack can fill the 8 GB of RAM, and
# without swap the server stalls (cloudflared and SSM stop answering) instead of slowing.
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

snap install aws-cli --classic

%{ if tailscale_key_param != null ~}
curl -fsSL https://tailscale.com/install.sh | sh
# No tracing while a secret is in play: this output also goes to the EC2 console log.
set +x
key=$(aws ssm get-parameter --region ${region} --name "${tailscale_key_param}" \
  --with-decryption --query Parameter.Value --output text)
# --ssh: Tailscale SSH, so no SSH port or key pair is needed.
tailscale up --auth-key="$key" --hostname=${tailscale_hostname} --ssh
unset key
set -x
%{ endif ~}

%{ if tunnel_token_param != null ~}
# cloudflared from Cloudflare's signed apt repo (updates with apt upgrade). Only with a
# domain; adding one later means running this block by hand (infra/README.md).
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  > /etc/apt/sources.list.d/cloudflared.list
apt-get update
apt-get install -y cloudflared
set +x # no tracing while a secret is in play (see above)
token=$(aws ssm get-parameter --region ${region} --name "${tunnel_token_param}" \
  --with-decryption --query Parameter.Value --output text)
cloudflared service install "$token" # systemd service; routes come from public.tf
unset token
set -x
%{ endif ~}
