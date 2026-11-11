#!/bin/bash
# First boot only (cloud-init). Installs Docker, just and Tailscale, then joins the
# tailnet. Deploying the repo is a manual step for now (infra/README.md).
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
