
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


## 📂 Project files

This project is structured into modular microservices, separating the edge routing, the language model agent, and the file system tools into distinct, containerized domains.

```text
.
├── agent/                  # Python LangChain integration and agent logic
│   ├── langchain_test.py   # Unit tests for the agent and tools
│   └── server.py           # FastAPI server exposing the agent endpoints
├── caddy/                  # Edge router and reverse proxy
│   ├── Caddyfile           # TLS and reverse proxy configuration
│   └── caddy_test.sh       # Validation script for Caddy configuration
├── fileserver/             # Golang MCP (Model Context Protocol) file server
│   ├── go.mod              # Go module dependencies
│   ├── main.go             # Core MCP server logic and tool handlers
│   └── mcp_test.go         # Unit tests for the Go MCP handlers
├── proxy/                  # Local proxy wrappers and routing
│   ├── proxy_config.yaml   # Proxy configuration rules
│   └── proxy_wrapper.py    # Python wrapper for proxy execution
├── docker-compose.yml      # Orchestrates the Caddy, Agent, and MCP containers
├── Dockerfile.langchain    # Container build steps for the Python agent
├── Dockerfile.mcp          # Container build steps for the Go fileserver
├── init_build.sh           # Initial environment setup and build script
├── query.sh                # CLI utility for sending test queries to the agent
├── run.sh                  # Operational script (generates certs, manages lifecycle)
├── test.sh                 # Master test suite (runs unit and integration tests)
└── README.md               # Project documentation
```

## 🛠️ Operational Commands

### Initialize and Start
The `run.sh` script automates certificate generation, token rotation, and container orchestration:
```bash
./run.sh
./query.sh "Please read info.txt from my workspace."
```