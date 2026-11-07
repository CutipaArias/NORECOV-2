#!/usr/bin/env bash
set -euo pipefail

# postStartCommand can still be running while the user manually starts the
# demo. Serialize those calls so Compose never races to create the same names.
exec 9>/tmp/norecov-codespaces-setup.lock
if ! flock -n 9; then
  echo "El inicio de NORECOV ya está en curso; espera a que termine."
  exit 0
fi

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  python3 scripts/generate_env.py
fi

# Docker-in-Docker starts with the Codespace container. Wait for its daemon
# before running Compose so a slow first boot does not fail immediately.
docker_ready=false
for _ in $(seq 1 60); do
  if docker info >/dev/null 2>&1; then
    docker_ready=true
    break
  fi
  sleep 2
done

if [[ "$docker_ready" != true ]]; then
  echo "Docker no respondió en 120 segundos; revisa el registro del contenedor." >&2
  exit 1
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
