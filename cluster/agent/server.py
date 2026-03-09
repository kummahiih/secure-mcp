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
import setuplogging
from runenv import MCP_SERVER_URL, MCP_API_TOKEN, LANGCHAIN_API_TOKEN, OPENAI_API_KEY
from files_mcp import read_workspace_file, delete_file, create_file, write_file, list_files



logger = logging.getLogger(__name__)


app = FastAPI(title="Secure LangChain Server")
security = HTTPBearer()


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

tools = [read_workspace_file, delete_file, create_file, write_file, list_files]

# The agent now uses the ephemeral key to authenticate with the LiteLLM proxy


agents = {
    "remote": create_agent(
        ChatOpenAI(
            model="gemini-flash",
            api_key=OPENAI_API_KEY,            # Explicitly passing the ephemeral key
            base_url="https://proxy:4000/v1", # Routing to the 'proxy' service on port 4000
            temperature=0
            ),
        tools=tools),
    "local": create_agent(
        ChatOpenAI(
            model="qwen-coder",
            api_key=OPENAI_API_KEY,            # Explicitly passing the ephemeral key
            base_url="https://proxy:4000/v1", # Routing to the 'proxy' service on port 4000
            temperature=0
            ),
        tools=tools),
}
    

class QueryRequest(BaseModel):
    query: str
    model: str

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
        agent = agents[request.model]
        
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
    uvicorn.run(
        app, # Or "server:app" depending on your setup
        host="0.0.0.0",
        port=8000,
        # Enable HTTPS using the container's internal certificates
        ssl_keyfile="/app/certs/agent.key",
        ssl_certfile="/app/certs/agent.crt"
    )