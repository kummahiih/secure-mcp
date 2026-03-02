import os
import sys
import base64
from unittest.mock import patch

# --- THE HACK: FORCE LOCAL LOADING ---
def robust_mock_load(tiktoken_bpe_file, *args, **kwargs):
    local_file_path = "/tmp/tiktoken_cache/9b5ad716431e6077c748b039600b13ad"
    if not os.path.exists(local_file_path):
        print(f"[ERROR] Mock failed: {local_file_path} not found!")
        sys.exit(1)
        
    with open(local_file_path, "rb") as f:
        # Re-implementing parsing logic for Tiktoken's expected format
        return {
            base64.b64decode(parts[0]): int(parts[1])
            for line in f
            if (parts := line.split())
        }

# --- ENVIRONMENT CONFIGURATION ---
# These must be set BEFORE importing litellm to ensure internal clients pick them up
os.environ["HTTP_PROXY"] = "http://caddy-sidecar:8080"
os.environ["HTTPS_PROXY"] = "http://caddy-sidecar:8080"
os.environ["NO_PROXY"] = "localhost,127.0.0.1,mcp-server,langchain-server,caddy-sidecar,proxy"

# Re-affirm keys from Docker environment
os.environ["LITELLM_MASTER_KEY"] = os.getenv("LITELLM_MASTER_KEY", "")
os.environ["OLLAMA_API_KEY"] = os.getenv("OLLAMA_API_KEY", "")

# Apply the patch and launch LiteLLM
with patch("tiktoken.load.load_tiktoken_bpe", side_effect=robust_mock_load):
    print("[HACK] Tiktoken fetcher successfully mocked.")
    print(f"[INFO] Routing egress via: {os.environ['HTTP_PROXY']}")
    
    # Import here so it sees the modified environment
    from litellm.proxy.proxy_cli import run_server
    
    if __name__ == "__main__":
        # sys.argv mimics CLI arguments for the run_server function
        sys.argv = [
            "litellm", 
            "--config", "/tmp/config.yaml", 
            "--port", "4000", 
            "--host", "0.0.0.0"
        ]
        run_server()