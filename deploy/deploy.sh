#!/bin/sh
set -eu

docker compose up -d --build --remove-orphans

attempt=0
until curl -fsS http://127.0.0.1:8000/health >/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 20 ]; then
        docker compose logs --tail=100 web
        exit 1
    fi
    sleep 2
done

docker compose ps
