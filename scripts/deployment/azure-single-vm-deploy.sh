#!/usr/bin/env bash
set -euo pipefail

domain="${1:?usage: azure-single-vm-deploy.sh <domain> [repository-root]}"
repository_root="${2:-/home/opensailadmin/opensail}"

cd "$repository_root"
cp .env.example .env

export OPENSAIL_SECRET_KEY="$(openssl rand -hex 32)"
export OPENSAIL_INTERNAL_SECRET="$(openssl rand -hex 32)"
export OPENSAIL_POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export OPENSAIL_CSRF_SECRET="$(openssl rand -hex 32)"
export OPENSAIL_CHANNEL_KEY="$(openssl rand -base64 32 | tr '+/' '-_')"
export OPENSAIL_DOMAIN="$domain"

python3 - <<'PY'
import os
from pathlib import Path

path = Path(".env")
domain = os.environ["OPENSAIL_DOMAIN"]
updates = {
    "SECRET_KEY": os.environ["OPENSAIL_SECRET_KEY"],
    "INTERNAL_API_SECRET": os.environ["OPENSAIL_INTERNAL_SECRET"],
    "POSTGRES_DB": "tesslate_dev",
    "POSTGRES_USER": "tesslate_user",
    "POSTGRES_PASSWORD": os.environ["OPENSAIL_POSTGRES_PASSWORD"],
    "LITELLM_API_BASE": "",
    "LITELLM_MASTER_KEY": "",
    "LITELLM_DEFAULT_MODELS": "gpt-4.1-mini",
    "APP_DOMAIN": domain,
    "APP_PROTOCOL": "http",
    "VITE_API_URL": f"http://{domain}",
    "CORS_ORIGINS": f"http://{domain}",
    "ALLOWED_HOSTS": domain,
    "COOKIE_SECURE": "false",
    "COOKIE_DOMAIN": f".{domain}",
    "CSRF_SECRET_KEY": os.environ["OPENSAIL_CSRF_SECRET"],
    "CHANNEL_ENCRYPTION_KEY": os.environ["OPENSAIL_CHANNEL_KEY"],
    "STRIPE_SECRET_KEY": "",
    "STRIPE_PUBLISHABLE_KEY": "",
    "STRIPE_WEBHOOK_SECRET": "",
}

lines = path.read_text().splitlines()
rendered = []
seen = set()
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    rendered.append(line)

for key, value in updates.items():
    if key not in seen:
        rendered.append(f"{key}={value}")

path.write_text("\n".join(rendered) + "\n")
PY

chmod 600 .env
mkdir -p traefik
touch traefik/acme.json
chmod 600 traefik/acme.json

sudo docker compose config --quiet
sudo docker compose build
sudo docker compose up -d postgres redis
sudo docker compose run --rm --no-deps orchestrator alembic upgrade head
sudo docker compose up -d --remove-orphans