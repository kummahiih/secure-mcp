#!/bin/bash
# caddy_test.sh

# Run the validation with the same user mapping and environment overrides
docker run --rm \
    --user "1000:1000" \
    -e XDG_DATA_HOME=/tmp/caddy_data \
    -e XDG_CONFIG_HOME=/tmp/caddy_config \
    -v "$(pwd)/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$(pwd)/certs:/certs:ro" \
    caddy:2-alpine \
    caddy validate --config /etc/caddy/Caddyfile