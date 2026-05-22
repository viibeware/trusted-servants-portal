#!/usr/bin/env bash
# Launch the TSP Pro public demo with one command.
# Builds the image, ensures a secret key, and brings the demo up on :8090.
set -euo pipefail

# Move to the repo root (this script lives in demo/).
cd "$(dirname "$0")/.."

# Ensure a TSP_SECRET_KEY exists in .env (compose reads it from there).
if [ ! -f .env ] || ! grep -q '^TSP_SECRET_KEY=' .env; then
  if command -v openssl >/dev/null 2>&1; then
    KEY="$(openssl rand -hex 32)"
  else
    KEY="$(head -c 48 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 64)"
  fi
  echo "TSP_SECRET_KEY=${KEY}" >> .env
  echo "→ Generated a TSP_SECRET_KEY in .env"
fi

echo "→ Building and starting the TSP Pro demo…"
docker compose -f docker-compose.demo.yml up -d --build

cat <<'EOF'

  ✅ TSP Pro demo is starting.

     Product page : http://localhost:8090/            (marketing homepage)
     Live demo    : http://localhost:8090/demo         (the fellowship site)
     Admin backend: http://localhost:8090/demo/login-admin   (one-click, or /tspro · admin / admin)

  First boot seeds the demo fellowship (Meridian Recovery Collective);
  give it a few seconds. Logs:   docker compose -f docker-compose.demo.yml logs -f
  Stop:                          docker compose -f docker-compose.demo.yml down
  Reset to a fresh seed:         docker compose -f docker-compose.demo.yml down -v
EOF
