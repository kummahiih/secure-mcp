import os
import logging
import secrets
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import requests
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
import json


# Configure logging to use a 24-hour clock format
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Environment variables injected by Docker Compose / run.sh
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp-server:8443")
MCP_API_TOKEN = os.getenv("MCP_API_TOKEN")
LANGCHAIN_API_TOKEN = os.getenv("LANGCHAIN_API_TOKEN")

app = FastAPI(title="Secure LangChain Server")
security = HTTPBearer()

# Ensure we have the key, otherwise the agent will fail silently with 401s
dynamic_key = os.getenv("OPENAI_API_KEY")
if not dynamic_key:
    logging.error("DYNAMIC_AGENT_KEY (passed as OPENAI_API_KEY) is not set!")

# The agent now uses the ephemeral key to authenticate with the LiteLLM proxy
llm = ChatOpenAI(
    model="qwen-coder",             
    api_key=dynamic_key,            # Explicitly passing the ephemeral key
    base_url="http://proxy:4000/v1", # Routing to the 'proxy' service on port 4000
    temperature=0
)


def verify_langchain_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validates the Bearer token in constant time to prevent timing attacks."""
    if not LANGCHAIN_API_TOKEN:
        logger.error("LANGCHAIN_API_TOKEN is not configured on the server.")
        raise HTTPException(status_code=500, detail="Server configuration error.")
    
    # compare_digest ensures the comparison takes the same amount of time regardless of correctness
    if not secrets.compare_digest(credentials.credentials, LANGCHAIN_API_TOKEN):
        logger.warning("Failed authentication attempt on /ask endpoint.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

@tool
def read_workspace_file(file_path: str) -> str:
    """Reads the contents of a file from the secure Go MCP workspace."""
    if not MCP_API_TOKEN:
        return "Error: MCP_API_TOKEN is not configured."

    headers = {"Authorization": f"Bearer {MCP_API_TOKEN}"}
    endpoint = f"{MCP_SERVER_URL}/read?path={file_path}"
    
    try:
        logger.info(f"Requesting file: {file_path}")
        response = requests.get(endpoint, headers=headers, verify="/certs/ca.crt", timeout=10)
        logger.info(f"Server returned {response.status_code} {response.text}")

        if response.status_code == 200:
            return response.text
        elif response.status_code == 401:
            return "Error: Unauthorized. Token mismatch."
        elif response.status_code == 404:
            return "Error: File not found or access denied by OS jail."
        else:
            return f"Error: Server returned status {response.status_code}"
            
    except requests.exceptions.SSLError as e:
        logger.error(f"TLS Verification failed: {e}")
        return "Error: Secure connection failed (TLS/SSL)."
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return f"Error: {str(e)}"

@tool
def delete_file(path: str):
    """Removes a file from the workspace."""
    resp = requests.delete(f"{MCP_SERVER_URL}/remove?path={path}", 
                           headers={"Authorization": f"Bearer {MCP_API_TOKEN}"},
                           verify="/certs/ca.crt")
    return "File deleted" if resp.status_code == 200 else f"Error: {resp.text}"

@tool
def create_file(path: str):
    """Creates a new empty file in the workspace."""
    resp = requests.post(f"{MCP_SERVER_URL}/create?path={path}", 
                         headers={"Authorization": f"Bearer {MCP_API_TOKEN}"},
                         verify="/certs/ca.crt")
    return "File created" if resp.status_code == 201 else f"Error: {resp.text}"

@tool
def write_file(path: str, content: str) -> str:
    """
    Overwrites the entire content of a file with new content. 
    Use this to update files or create new ones with specific data.
    """
    url = f"{MCP_SERVER_URL}/write"
    payload = {"path": path, "content": content}
    headers = {"Authorization": f"Bearer {MCP_API_TOKEN}"}
    
    try:
        # verify="/certs/ca.crt" ensures the internal TLS is trusted
        response = requests.post(url, json=payload, headers=headers, verify="/certs/ca.crt")
        
        if response.status_code == 200:
            return f"Successfully wrote to {path}"
        else:
            return f"Failed to write file: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error connecting to MCP server: {str(e)}"



@tool
def list_files() -> str:
    """
    Recursively lists all files and directories in the workspace.
    Returns a JSON string containing the list of paths.
    """
    url = f"{MCP_SERVER_URL}/list"
    headers = {"Authorization": f"Bearer {MCP_API_TOKEN}"}
    
    try:
        response = requests.get(url, headers=headers, verify="/certs/ca.crt")
        if response.status_code == 200:
            files = response.json().get("files", [])
            # Always return a JSON object for unambiguous parsing
            return json.dumps({"files": files, "count": len(files)})
        else:
            return json.dumps({"error": f"HTTP {response.status_code}", "detail": response.text})
    except Exception as e:
        return json.dumps({"error": "connection_failed", "detail": str(e)})


tools = [read_workspace_file, delete_file, create_file, write_file, list_files]
agent = create_agent(llm, tools=tools)

class QueryRequest(BaseModel):
    query: str

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/ask")
async def ask_agent(request: QueryRequest, token: str = Depends(verify_langchain_token)):
    """External endpoint routed through Caddy, secured with Bearer token."""
    logger.info(f"Received authenticated query: {request.query}")
    try:
        inputs = {
            "messages": [
                ("system", "You are a helpful assistant with access to a local workspace. "
                           "When asked to read a file, use the available tools. "
                           "Once you receive the file content, summarize it or provide it "
                           "to the user immediately. Do not repeat the same tool call."),
                ("user", request.query)
            ]
        }
        
        result = agent.invoke(inputs)
        
        final_answer = ""
        
        # 1. Safely check for LangGraph's "messages" structure
        if isinstance(result, dict) and "messages" in result:
            # Search backwards for the actual AI response
            for msg in reversed(result["messages"]):
                if msg.type == "ai" and msg.content:
                    final_answer = msg.content
                    break
            
            # 2. If no text was found, extract the exact tool call or raw object
            if not final_answer:
                last_msg = result["messages"][-1]
                tool_calls = getattr(last_msg, "tool_calls", [])
                
                if tool_calls:
                    final_answer = f"DIAGNOSTIC: Agent generated a tool call but the loop stopped executing. Tool requested: {tool_calls}"
                else:
                    final_answer = f"DIAGNOSTIC: Agent returned no content and no tool calls. Last message: {last_msg}"
        else:
            # 3. Fallback for standard LangChain AgentExecutor
            final_answer = result.get("output", str(result))

        return {"response": final_answer}
        
    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)