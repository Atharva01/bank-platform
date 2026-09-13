#!/bin/bash
# One-time host setup, run automatically as EC2 user-data on first boot.
# Installs Docker + the Compose plugin and creates the traefik-public
# network (docker-compose.prod.yml's external network, see CLAUDE.md's
# "Deploying" section) - everything after this point (checking out the
# repos, placing .env, `docker compose -f docker-compose.prod.yml up -d`)
# is still a manual step, same as the original bare-VPS plan, since it
# needs the real .env placed by hand rather than baked into user-data
# (which is visible via the instance metadata service - not a safe place
# for secrets).
set -euo pipefail

# AL2023 ships Docker directly through dnf - no amazon-linux-extras needed.
dnf update -y
dnf install -y docker

systemctl enable --now docker

# Compose v2 as the CLI plugin (`docker compose`, not the standalone
# docker-compose binary) - matches what local dev already uses.
mkdir -p /usr/local/lib/docker/cli-plugins
COMPOSE_VERSION="v2.32.4"
curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Lets ec2-user run docker without sudo (takes effect on next login/session).
usermod -aG docker ec2-user

# One-time network creation (see docker-compose.prod.yml's header comment) -
# idempotent, safe to run again if this script is re-run.
docker network create traefik-public || true
