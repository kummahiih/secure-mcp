#!/bin/bash
set -e

echo "[$(date +'%H:%M:%S')] Starting automated test suite..."

echo "----------------------------------------"
echo "[$(date +'%H:%M:%S')] 1/4: Validating Caddy Edge Router..."
bash ./caddy_test.sh

echo "----------------------------------------"
echo "[$(date +'%H:%M:%S')] 2/4: Running Golang MCP Server Tests..."
go test mcp_test.go main.go -v

echo "----------------------------------------"
echo "[$(date +'%H:%M:%S')] 3/4: Running Python LangChain Tests..."
pytest langchain_test.py -v

echo "----------------------------------------"
echo "[$(date +'%H:%M:%S')] 4/4: Running Docker Integration Tests..."

# Provide completely fake tokens so the Python SDKs and Docker Compose don't crash on boot
export MCP_API_TOKEN="integration-test-mcp-token"
export LANGCHAIN_API_TOKEN="integration-test-langchain-token"
export OPENAI_API_KEY="sk-dummy-key-for-integration-tests"
export ANTHROPIC_API_KEY="dummy-anthropic-key"
export GEMINI_API_KEY="dummy-gemini-key"
export OLLAMA_API_KEY="dummy-ollama-key"

echo "[$(date +'%H:%M:%S')] Setting directory permissions for tests..."
chmod -R a+r certs || true
chmod 777 workspace || true

echo "[$(date +'%H:%M:%S')] Building containers..."
docker-compose build

echo "[$(date +'%H:%M:%S')] Starting containers..."
docker-compose up -d

echo "[$(date +'%H:%M:%S')] Waiting for Caddy and FastAPI to initialize (10s)..."
sleep 10

echo "[$(date +'%H:%M:%S')] Pinging the secured public Caddy endpoint..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8080/ask \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $LANGCHAIN_API_TOKEN" \
    -d '{"query": "Hello"}')

if [ "$HTTP_STATUS" -eq 200 ]; then
    echo "[$(date +'%H:%M:%S')] Success! Caddy routed the request. Endpoint returned 200 OK."
else
    echo "[$(date +'%H:%M:%S')] Error: Endpoint returned HTTP $HTTP_STATUS."
    echo "[$(date +'%H:%M:%S')] Dumping container logs for debugging:"
    docker-compose logs
    docker-compose down
    exit 1
fi

echo "[$(date +'%H:%M:%S')] Tearing down integration containers..."
docker-compose down

echo "----------------------------------------"
echo "[$(date +'%H:%M:%S')] All unit and integration tests passed successfully!"