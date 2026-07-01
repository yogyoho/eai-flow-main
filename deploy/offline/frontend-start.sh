#!/bin/sh
# Frontend startup: ensure allowedDevOrigins includes the intranet host(s).
#
# Next.js 16 dev mode rejects RSC requests whose origin is not localhost unless
# the host is listed in `allowedDevOrigins` (next.config.js). Behind an nginx
# reverse proxy accessed via server IP/FQDN, this blocks RSC hydration — the page
# renders static HTML but client components (login button, etc.) never mount.
#
# Configure via env (in .env, surfaced to the frontend container):
#   INTRANET_HOSTS="10.180.41.157,eai.prod.local"
# Falls back to localhost + the docker service name.
set -e
CONFIG=/app/frontend/next.config.js
HOSTS="${INTRANET_HOSTS:-}"
[ -z "$HOSTS" ] && HOSTS="localhost"

# Build a JS array string: ["h1","h2"]
ORIGINS=""
IFS=','
for h in $HOSTS; do
  h=$(echo "$h" | tr -d ' ')
  [ -z "$h" ] && continue
  ORIGINS="${ORIGINS}\"${h}\","
done
ORIGINS="[${ORIGINS%,}]"

if [ -f "$CONFIG" ] && ! grep -q "allowedDevOrigins" "$CONFIG" 2>/dev/null; then
  sed -i "s/devIndicators: false/devIndicators: false,\n  allowedDevOrigins: ${ORIGINS}/" "$CONFIG" || true
  echo "[frontend-start] injected allowedDevOrigins: ${ORIGINS}"
fi

cd /app/frontend
exec pnpm dev --port 3000 --hostname 0.0.0.0
