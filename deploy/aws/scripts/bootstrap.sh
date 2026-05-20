#!/bin/bash
# EC2 bootstrap: install app, systemd, nginx. Run as root on Ubuntu 22.04.
set -euo pipefail

APP_DIR="/opt/ai-incident-resolution"
REPO_URL="${REPO_URL:-https://github.com/soujanya1604/ai-incident-resolution.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y git python3.11 python3.11-venv python3.11-dev nginx build-essential

rm -rf "$APP_DIR"
git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"

sudo -u ubuntu bash <<'UV'
set -euo pipefail
cd /opt/ai-incident-resolution
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
UV

if [[ -z "$OPENAI_API_KEY" ]]; then
  echo "ERROR: OPENAI_API_KEY is required for bootstrap." >&2
  exit 1
fi

cat > "$APP_DIR/.env" <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
API_URL=http://127.0.0.1:8001
API_PORT=8001
EOF
chmod 600 "$APP_DIR/.env"
chown ubuntu:ubuntu "$APP_DIR/.env"

install -m 644 "$APP_DIR/deploy/aws/systemd/ai-incident-api.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/aws/systemd/ai-incident-ui.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/aws/nginx/ai-incident.conf" /etc/nginx/sites-available/ai-incident
ln -sf /etc/nginx/sites-available/ai-incident /etc/nginx/sites-enabled/ai-incident
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable ai-incident-api ai-incident-ui nginx
systemctl start ai-incident-api
sleep 20
systemctl start ai-incident-ui
nginx -t && systemctl reload nginx

echo "Bootstrap complete."
