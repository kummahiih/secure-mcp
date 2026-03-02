import os
import sys
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

# 1. Inject dummy keys BEFORE importing server.py
os.environ["OPENAI_API_KEY"] = "sk-dummy-test-key-for-local-pytest-only"
os.environ["MCP_API_TOKEN"] = "dummy-mcp-token-for-tests"
os.environ["LANGCHAIN_API_TOKEN"] = "secure-test-token"

# Ensure the local directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from server import app, read_workspace_file


client = TestClient(app)

@patch("server.requests.get")
def test_read_workspace_tool(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = "mocked secure data"
    
    result = read_workspace_file.invoke({"file_path": "config.json"})
    assert result == "mocked secure data"
    mock_get.assert_called_once()

def test_fastapi_endpoint_unauthorized():
    # 1. Test missing token entirely (Modern FastAPI HTTPBearer returns 401)
    response = client.post("/ask", json={"query": "What is the status?"})
    assert response.status_code == 401
    
    # 2. Test invalid token (Our verify_langchain_token logic returns 401)
    headers = {"Authorization": "Bearer completely-wrong-token"}
    response = client.post("/ask", headers=headers, json={"query": "What is the status?"})
    assert response.status_code == 401

def test_fastapi_endpoint_authorized():
    # 3. Test successful authorization
    headers = {"Authorization": f"Bearer {os.environ['LANGCHAIN_API_TOKEN']}"}
    response = client.post("/ask", headers=headers, json={"query": "What is the status?"})
    
    # Returns 200 OK, even if the dummy LLM key generates an internal "error" json
    assert response.status_code == 200
    json_response = response.json()
    assert "response" in json_response or "error" in json_response


from server import delete_file, create_file, write_file, list_files

# --- Tool Logic Tests ---

@patch("server.requests.post")
def test_write_workspace_tool(mock_post):
    # Mock successful write
    mock_post.return_value.status_code = 200
    
    result = write_file.invoke({"path": "test.txt", "content": "hello"})
    assert "Successfully wrote to test.txt" in result
    
    # Verify the payload sent to MCP
    args, kwargs = mock_post.call_args
    assert kwargs["json"] == {"path": "test.txt", "content": "hello"}

@patch("server.requests.get")
def test_list_workspace_files_tool(mock_get):
    # Mock the JSON response from Go MCP server
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "files": ["main.go", "subdir/test.py"],
        "count": 2
    }
    
    result_str = list_files.invoke({})
    import json
    result_data = json.loads(result_str)
    
    assert result_data["count"] == 2
    assert "main.go" in result_data["files"]

@patch("server.requests.post")
def test_create_workspace_file_tool(mock_post):
    mock_post.return_value.status_code = 201
    
    result = create_file.invoke({"path": "empty.txt"})

    # Unpack the call arguments safely
    args, kwargs = mock_post.call_args

    # args[0] is the URL passed to requests.post
    assert "empty.txt" in args[0]

    assert "File created" in result

@patch("server.requests.delete")
def test_delete_workspace_file_tool(mock_delete):
    mock_delete.return_value.status_code = 200
    
    result = delete_file.invoke({"path": "temp.log"})
    assert "File deleted" in result

# --- Error Handling & Edge Cases ---

@patch("server.requests.get")
def test_read_tool_error_handling(mock_get):
    # Test how the tool handles a 404 from the MCP server
    mock_get.return_value.status_code = 404
    mock_get.return_value.text = "File not found"
    
    result = read_workspace_file.invoke({"file_path": "missing.txt"})
    assert "File not found or access denied by OS jail." in result

@patch("server.requests.get")
def test_list_tool_connection_failure(mock_get):
    # Simulate a network timeout or connection refused
    mock_get.side_effect = Exception("Connection Refused")
    
    result = list_files.invoke({})
    assert "Error connecting to MCP server" in result

# --- Security Headers Check ---

@patch("server.requests.get")
def test_list_tool_connection_failure(mock_get):
    # Simulate a network timeout or connection refused
    mock_get.side_effect = Exception("Connection Refused")
    
    # Use the exact tool name from your server.py (e.g., list_files)
    result = list_files.invoke({}) 
    
    # Assert that the new JSON error format is present
    assert "connection_failed" in result
    assert "Connection Refused" in result