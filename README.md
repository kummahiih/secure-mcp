
# 🛡️ Secure MCP Cluster

A hardened, containerized environment for AI Agents to interact with local system tools via the Model Context Protocol (MCP). This setup utilizes a sidecar architecture to enforce TLS encryption and token-based authentication across all internal services.

## 🏗️ System Architecture



### Service Roles
* **Caddy Sidecar**: The gateway. Handles SSL termination (TLS 1.3) and provides a secure ingress point to the internal network.
* **LangChain Server**: The orchestrator. Runs the LangGraph/Agent logic and coordinates between the LLM and local tools.
* **LiteLLM Proxy**: The API gateway. Provides a unified interface for LLM providers (Ollama, OpenAI, etc.) while managing egress credentials.
* **MCP Server (Go 1.24)**: The execution layer. A secure Go service using `os.OpenRoot` to provide restricted filesystem access to the `/workspace` volume.

---

## 🔌 Network Topology

The cluster enforces an "Air-Gap" style isolation using two distinct Docker networks:

| Service | Network | Exposure |
| :--- | :--- | :--- |
| **Caddy Sidecar** | `ext_net`, `int_net` | **Public**: Port 8443 |
| **LangChain Server** | `int_net` | Internal Only |
| **LiteLLM Proxy** | `int_net` | Internal Only |
| **MCP Server** | `int_net` | Internal Only |

### Internal Communication Path
1.  **User Request**: `Host` -> `https://localhost:8443` -> `Caddy`
2.  **Logic Processing**: `Caddy` -> `http://langchain-server:8000`
3.  **Tool Execution**: `LangChain` -> `https://mcp-server:8443/read`
4.  **Inference**: `LangChain` -> `http://proxy:4000/v1/chat/completions`

---

## 🔒 Security Guardrails

### 1. Unified Trust Chain
All services mount a shared `./certs` volume. By setting the `SSL_CERT_FILE` environment variable, every container (Python, Go, and Caddy) trusts the internal Root CA, allowing for seamless internal HTTPS without `InsecureRequestWarning`.

### 2. Filesystem Jail (Go 1.24 OpenRoot)
The MCP server implements the new `os.OpenRoot` capability. This creates a logical "jail" at `/workspace`. Even if an agent is prompted to perform a directory traversal attack (e.g., `../../etc/passwd`), the Go runtime will block the request at the system level.

### 3. Dual-Layer Authentication
* **Ingress Auth**: Managed by Caddy/FastAPI via `LANGCHAIN_API_TOKEN`.
* **Service Auth**: The LangChain server communicates with the MCP server using a dedicated `MCP_API_TOKEN`.

---

## 📂 Project Structure

```text
.
├── 🐳 Docker & Orchestration
│   ├── docker-compose.yml       # Primary service orchestration
│   ├── Dockerfile.langchain     # Python environment for the AI Agent
│   ├── Dockerfile.mcp           # Go 1.24 environment for the Tool server
│   └── Caddyfile                # Reverse proxy & TLS configuration
│
├── ⚙️ Core Logic
│   ├── main.go                  # MCP Server (Go) - Secure file handler
│   ├── server.py                # LangChain Server (Python) - Agent logic
│   ├── proxy_wrapper.py         # LiteLLM customization layer
│   └── proxy_config.yaml        # LiteLLM routing rules
│
├── 🔑 Security & Assets
│   ├── certs/                   # Generated CA, Certs, and Keys (Auto-generated)
│   ├── workspace/               # Shared data volume for AI file access
│   └── cl100k_base.tiktoken     # Offline tokenizer cache for LiteLLM
│
├── 🚀 Scripts & Automation
│   ├── run.sh                   # Main entry: Generates certs and boots cluster
│   ├── query.sh                 # Client script to send queries to the agent
│   ├── init_build.sh            # One-time build initialization
│   └── test.sh                  # Comprehensive cluster health check
│
└── 🧪 Debugging Tools
    ├── caddy_test.sh            # Validates proxy routing
    ├── mcp_test.go              # Unit tests for Go tool logic
    └── langchain_test.py        # Validates Agent-Proxy communication
```


## 🛠️ Operational Commands

### Initialize and Start
The `run.sh` script automates certificate generation, token rotation, and container orchestration:
```bash
./run.sh