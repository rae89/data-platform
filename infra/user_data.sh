#!/bin/bash
# First boot only (cloud-init). Installs Docker and just; optionally joins Tailscale.
# Deploying the repo is a manual step for now (infra/README.md).
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
