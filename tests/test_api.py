"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from llm_client import app
from models import BlockRef


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_block_ref_dict():
    """Create a mock block ref dictionary."""
    return {
        "repo_owner": "test-owner",
        "repo_name": "test-repo",
        "ref": "main",
        "path": "src/test.py",
        "start_line": 10,
        "end_line": 20,
    }


class TestChatEndpoint:
    """Tests for /chat endpoint."""
    
    @patch("llm_client.agent")
    def test_chat_endpoint_success(self, mock_agent, client, mock_block_ref_dict):
        """Test successful chat request."""
        mock_agent.answer_question.return_value = "Test answer"
        
        response = client.post(
            "/chat",
            json={
                "block_ref": mock_block_ref_dict,
                "question": "What does this code do?",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert data["answer"] == "Test answer"
    
    @patch("llm_client.agent")
    def test_chat_endpoint_git_error(self, mock_agent, client, mock_block_ref_dict):
        """Test chat endpoint with GitError."""
        from git_core import GitError
        mock_agent.answer_question.side_effect = GitError("Repo not found")
        
        response = client.post(
            "/chat",
            json={
                "block_ref": mock_block_ref_dict,
                "question": "What does this code do?",
            },
        )
        
        assert response.status_code == 400
        assert "Git error" in response.json()["detail"]
    
    def test_chat_endpoint_invalid_request(self, client):
        """Test chat endpoint with invalid request."""
        response = client.post(
            "/chat",
            json={
                "block_ref": {
                    "repo_owner": "test",
                    "repo_name": "test",
                    "ref": "main",
                    "path": "test.py",
                    "start_line": 0,  # Invalid
                    "end_line": 10,
                },
                "question": "Test",
            },
        )
        
        # Should return validation error
        assert response.status_code == 422


class TestLinearEndpoints:
    """Tests for Linear endpoints."""
    
    @patch("llm_client.linear_client")
    def test_get_linear_teams_success(self, mock_linear_client, client):
        """Test getting Linear teams successfully."""
        mock_linear_client.get_teams.return_value = [
            {
                "id": "team-1",
                "key": "ENG",
                "name": "Engineering",
            }
        ]
        
        response = client.get("/linear/teams")
        
        assert response.status_code == 200
        data = response.json()
        assert "teams" in data
        assert len(data["teams"]) == 1
    
    def test_get_linear_teams_not_configured(self, client, monkeypatch):
        """Test getting teams when Linear is not configured."""
        # Set linear_client to None
        import llm_client
        original_client = llm_client.linear_client
        llm_client.linear_client = None
        
        try:
            response = client.get("/linear/teams")
            assert response.status_code == 503
        finally:
            llm_client.linear_client = original_client
    
    @patch("llm_client.linear_client")
    def test_search_linear_issues(self, mock_linear_client, client):
        """Test searching Linear issues."""
        from tools import search_linear_issues_tool
        from models import LinearIssue
        
        # Mock the tool
        with patch("tools.search_linear_issues_tool") as mock_search:
            mock_search.return_value = [
                LinearIssue(
                    id="issue-1",
                    identifier="ENG-1",
                    title="Test Issue",
                    description="Test",
                    url="https://linear.app/test/ENG-1",
                    priority=1,
                )
            ]
            
            response = client.post(
                "/linear/issues/search",
                json={
                    "query": "test",
                    "limit": 10,
                },
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "issues" in data
            assert len(data["issues"]) == 1
    
    @patch("llm_client.linear_client")
    def test_create_linear_issue(self, mock_linear_client, client):
        """Test creating a Linear issue."""
        from tools import create_linear_issue_tool
        from models import LinearIssue
        
        # Mock the tool
        with patch("tools.create_linear_issue_tool") as mock_create:
            mock_create.return_value = LinearIssue(
                id="issue-1",
                identifier="ENG-1",
                title="New Issue",
                description="Description",
                url="https://linear.app/test/ENG-1",
                priority=1,
            )
            
            response = client.post(
                "/linear/issues",
                json={
                    "team_id": "team-1",
                    "title": "New Issue",
                    "description": "Description",
                },
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["identifier"] == "ENG-1"
            assert data["title"] == "New Issue"


class TestCORS:
    """Tests for CORS headers."""
    
    def test_cors_headers(self, client, mock_block_ref_dict):
        """Test CORS headers are present."""
        with patch("llm_client.agent") as mock_agent:
            mock_agent.answer_question.return_value = "Test"
            
            response = client.options("/chat")
            assert response.status_code == 200
            
            response = client.post(
                "/chat",
                json={
                    "block_ref": mock_block_ref_dict,
                    "question": "Test",
                },
                headers={"Origin": "http://localhost:5173"},
            )
            
            assert "Access-Control-Allow-Origin" in response.headers

