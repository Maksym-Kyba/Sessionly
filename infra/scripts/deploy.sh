#!/usr/bin/env bash
# Deploys a branch of the public GitHub repository to the Sessionly server.
#
# Usage: infra/scripts/deploy.sh [branch]        (default branch: main)
# Requires: Terraform outputs from infra/terraform and infra/.env already present on the server.

set -euo pipefail

BRANCH="${1:-main}"
REPOSITORY_URL="https://github.com/Maksym-Kyba/Sessionly.git"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/sessionly}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST="$(terraform -chdir="$SCRIPT_DIR/../terraform" output -raw public_ip)"
echo "Deploying branch '$BRANCH' to $HOST"

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "ubuntu@$HOST" bash -s -- "$BRANCH" "$REPOSITORY_URL" <<'REMOTE'
set -euo pipefail
BRANCH="$1"
REPOSITORY_URL="$2"
APP_DIR=/opt/sessionly/app

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPOSITORY_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch --prune origin
git checkout -B "$BRANCH" "origin/$BRANCH"

if [ ! -f /opt/sessionly/.env ]; then
  echo "Missing /opt/sessionly/.env. Copy infra/.env.example there and fill it in." >&2
  exit 1
fi
cp /opt/sessionly/.env infra/.env
if [ -f /opt/sessionly/email.env ]; then
  install -m 600 /opt/sessionly/email.env infra/email.env
else
  install -m 600 infra/email.env.example infra/email.env
  echo "Gmail credentials are not configured; verification email delivery will fail closed." >&2
fi

cd infra
docker compose -f docker-compose.prod.yml --env-file .env up -d --build --remove-orphans
docker image prune -f
docker compose -f docker-compose.prod.yml ps
REMOTE
