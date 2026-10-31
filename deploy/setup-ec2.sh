#!/usr/bin/env bash
# One-time EC2 (Ubuntu 22.04/24.04) setup: installs Docker Engine + Compose plugin and creates the deploy directory.
# Run on the server:  bash setup-ec2.sh
set -euo pipefail

DEPLOY_DIR="${DEPLOY_DIR:-/opt/student-management}"

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

sudo mkdir -p "$DEPLOY_DIR"
sudo chown "$USER":"$USER" "$DEPLOY_DIR"

echo "Done. Log out and back in so the 'docker' group applies, then create $DEPLOY_DIR/.env (see .env.example)."
