#!/bin/bash
set -e
(
    . .env && \
    . .cluster_tokens.env && \
    . .secrets.env && \
    cd cluster && \
    docker-compose logs --tail 20 proxy && \
    docker-compose logs --tail 20 caddy-sidecar && \
    docker-compose logs --tail 10 langchain-server && \
    docker-compose logs --tail 10 mcp-server && \
    docker-compose logs --tail 10 mcp-server && \
    docker-compose logs --tail 10 mcp-server
)
    

