#!/usr/bin/env bash
set -euo pipefail

PROXY_HOST="${PROXY_HOST:-127.0.0.1}"
PROXY_PORT="${PROXY_PORT:-7890}"
USE_PROXY="${USE_PROXY:-1}"

cd "$(dirname "$0")"

if [[ "$USE_PROXY" != "0" ]]; then
  export https_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
  export http_proxy="http://${PROXY_HOST}:${PROXY_PORT}"
  export all_proxy="socks5://${PROXY_HOST}:${PROXY_PORT}"
fi

git pull

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

docker compose build
docker compose up -d
