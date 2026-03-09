import os
import logging
import requests
from langchain_core.tools import tool
import json
import setuplogging
from runenv import MCP_SERVER_URL, MCP_API_TOKEN, LANGCHAIN_API_TOKEN

logger = logging.getLogger(__name__)


@tool
def read_workspace_file(file_path: str) -> str:
    """Reads the contents of a file from the secure Go MCP workspace."""
    if not MCP_API_TOKEN:
        return "Error: MCP_API_TOKEN is not configured."

    headers = {"Authorization": f"Bearer {MCP_API_TOKEN}"}
    endpoint = f"{MCP_SERVER_URL}/read?path={file_path}"
    
    try:
        logger.info(f"Requesting file: {file_path}")
        response = requests.get(endpoint, headers=headers, verify="/app/certs/ca.crt", timeout=10)
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
                           verify="/app/certs/ca.crt")
    return "File deleted" if resp.status_code == 200 else f"Error: {resp.text}"

@tool
def create_file(path: str):
    """Creates a new empty file in the workspace."""
    resp = requests.post(f"{MCP_SERVER_URL}/create?path={path}", 
                         headers={"Authorization": f"Bearer {MCP_API_TOKEN}"},
                         verify="/app/certs/ca.crt")
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
        # verify="/app/certs/ca.crt" ensures the internal TLS is trusted
        response = requests.post(url, json=payload, headers=headers, verify="/app/certs/ca.crt")
        
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
        response = requests.get(url, headers=headers, verify="/app/certs/ca.crt")
        if response.status_code == 200:
            files = response.json().get("files", [])
            # Always return a JSON object for unambiguous parsing
            return json.dumps({"files": files, "count": len(files)})
        else:
            return json.dumps({"error": f"HTTP {response.status_code}", "detail": response.text})
    except Exception as e:
        return json.dumps({"error": "connection_failed", "detail": str(e)})

