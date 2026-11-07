#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  python3 scripts/generate_env.py
fi

docker compose --profile demo up -d --build --scale worker=2

ready=false
for _ in $(seq 1 60); do
  if docker compose --profile demo exec -T mongo-source sh -c \
      'mongosh --quiet -u "$DEMO_MONGO_USER" -p "$DEMO_MONGO_PASSWORD" --authenticationDatabase admin --eval "db.adminCommand({ping:1}).ok"' >/dev/null 2>&1 \
    && docker compose --profile demo exec -T redis-source sh -c \
      'REDISCLI_AUTH="$DEMO_REDIS_PASSWORD" redis-cli ping' >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done

if [[ "$ready" != true ]]; then
  echo "Los motores de demostración no respondieron a tiempo." >&2
  docker compose --profile demo ps
  exit 1
fi

python3 scripts/seed_demo.py
echo "NORECOV está listo. En Codespaces, comparte únicamente el puerto 8080."
