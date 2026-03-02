#!/bin/bash
set -e

# Uses a temporary, throwaway container to validate the Caddyfile syntax
docker run --rm \
    -v "$(pwd)/Caddyfile:/etc/caddy/Caddyfile" \
    caddy:2-alpine \
    caddy validate --config /etc/caddy/Caddyfile