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