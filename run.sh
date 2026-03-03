#!/bin/bash
set -e

echo "[$(date +'%H:%M:%S')] Starting cluster initialization..."

# 1. Load Secrets
if [ -f .secrets.env ]; then
    echo "[$(date +'%H:%M:%S')] Loading secrets from .secrets.env..."
    # We use 'allexport' to make sure these are available for the key validation loop
    set -a
    source .secrets.env
    set +a
else
    echo "[$(date +'%H:%M:%S')] Error: .secrets.env not found."
    exit 1
fi

# 2. Validate Keys
REQUIRED_KEYS=("ANTHROPIC_API_KEY" "OPENAI_API_KEY" "GEMINI_API_KEY" "OLLAMA_API_KEY" "HOST_DOMAIN")
for key in "${REQUIRED_KEYS[@]}"; do
    if [ -z "${!key}" ]; then
        echo "[$(date +'%H:%M:%S')] Error: $key is not set in .secrets.env."
        exit 1
    fi
done

# 3. Generate and Save Secure API Tokens
echo "[$(date +'%H:%M:%S')] Cleaning up old token files..."
rm -f .env .cluster_tokens.env

echo "[$(date +'%H:%M:%S')] Generating fresh cluster tokens..."
DYNAMIC_AGENT_KEY="sk-$(openssl rand -hex 16)"
MCP_API_TOKEN=$(openssl rand -hex 32)
LANGCHAIN_API_TOKEN=$(openssl rand -hex 32)

# Create the standard .env file for Docker Compose
# We append the .secrets.env content so Docker Compose has all keys in one place
{
    echo "DYNAMIC_AGENT_KEY=$DYNAMIC_AGENT_KEY"
    echo "MCP_API_TOKEN=$MCP_API_TOKEN"
    echo "LANGCHAIN_API_TOKEN=$LANGCHAIN_API_TOKEN"
} > .env

# Also keep the export-style file for query.sh compatibility
{
    echo "export DYNAMIC_AGENT_KEY=\"$DYNAMIC_AGENT_KEY\""
    echo "export MCP_API_TOKEN=\"$MCP_API_TOKEN\""
    echo "export LANGCHAIN_API_TOKEN=\"$LANGCHAIN_API_TOKEN\""
} > .cluster_tokens.env

# Ensure directories exist
mkdir -p certs workspace

# 4. Generate the Root Certificate Authority (CA)
if [ ! -f certs/ca.crt ]; then
    echo "[$(date +'%H:%M:%S')] Generating Root CA..."
    openssl genrsa -out certs/ca.key 4096
    openssl req -x509 -new -nodes -key certs/ca.key -sha256 -days 3650 \
        -out certs/ca.crt \
        -subj "/C=FI/ST=Uusimaa/L=Espoo/O=LocalCluster/CN=ClusterRootCA" >/dev/null 2>&1
fi

# 5. Generate the Leaf Certificate for the MCP Server
if [ ! -f certs/mcp.crt ]; then
    echo "[$(date +'%H:%M:%S')] Generating Leaf Certificate for MCP Server..."
    openssl genrsa -out certs/mcp.key 2048
    echo "subjectAltName=DNS:mcp-server,DNS:localhost,IP:127.0.0.1" > certs/mcp.ext
    openssl req -new -key certs/mcp.key -out certs/mcp.csr \
        -subj "/C=FI/ST=Uusimaa/L=Espoo/O=LocalCluster/CN=mcp-server" >/dev/null 2>&1
    openssl x509 -req -in certs/mcp.csr \
        -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
        -out certs/mcp.crt -days 365 -sha256 \
        -extfile certs/mcp.ext >/dev/null 2>&1
    rm certs/mcp.ext
fi

# 6. Prepare mounted directories
echo "[$(date +'%H:%M:%S')] Setting strict local directory permissions..."

# 750: You can do all, Group can read/enter, Others are completely blocked.
chmod 750 certs workspace

# 640: You can read/write, Group can read, Others get NOTHING.
chmod 640 certs/*

if [ ! -f proxy/9b5ad716431e6077c748b039600b13ad ]; then
    echo "[$(date +'%H:%M:%S')] Downloading tiktoken encoding map..."
    curl -s -o proxy/9b5ad716431e6077c748b039600b13ad https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken
fi

# --- NEW: Check for setup-only flag ---
if [[ "$1" == "--setup-only" ]]; then
    echo "[$(date +'%H:%M:%S')] Setup complete. Exiting due to --setup-only flag."
    exit 0
fi

# 7. Launch the stack
echo "[$(date +'%H:%M:%S')] Tearing down old containers..."
docker-compose down --rmi local --remove-orphans -v
docker image prune -f

echo "[$(date +'%H:%M:%S')] Building and Launching..."
docker-compose build
docker-compose up -d

echo "----------------------------------------"
echo "[$(date +'%H:%M:%S')] Cluster is up and running!"