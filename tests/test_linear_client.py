"""Tests for Linear client."""
import pytest
import responses
from unittest.mock import patch, Mock

from linear_client import LinearClient, LinearError


class TestLinearClient:
    """Tests for LinearClient."""
    
    def test_linear_client_init_without_key(self, monkeypatch):
        """Test LinearClient initialization without API key."""
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        with pytest.raises(LinearError, match="Linear API key not found"):
            LinearClient()
    
    def test_linear_client_init_with_key(self, monkeypatch):
        """Test LinearClient initialization with API key."""
        monkeypatch.setenv("LINEAR_API_KEY", "test-key")
        client = LinearClient()
        assert client.api_key == "test-key"
        assert "Bearer test-key" in client.headers["Authorization"]
    
    @responses.activate
    def test_get_teams_success(self, monkeypatch):
        """Test getting teams successfully."""
        monkeypatch.setenv("LINEAR_API_KEY", "test-key")
        client = LinearClient()
        
        # Mock API response
        responses.add(
            responses.POST,
            "https://api.linear.app/graphql",
            json={
                "data": {
                    "teams": {
                        "nodes": [
                            {
                                "id": "team-1",
                                "key": "ENG",
                                "name": "Engineering",
                            }
                        ]
                    }
                }
            },
            status=200,
        )
        
        teams = client.get_teams()
        assert len(teams) == 1
        assert teams[0]["id"] == "team-1"
        assert teams[0]["key"] == "ENG"
    
    @responses.activate
    def test_get_teams_api_error(self, monkeypatch):
        """Test handling API errors."""
        monkeypatch.setenv("LINEAR_API_KEY", "test-key")
        client = LinearClient()
        
        # Mock API error
        responses.add(
            responses.POST,
            "https://api.linear.app/graphql",
            json={
                "errors": [
                    {"message": "Unauthorized"}
                ]
            },
            status=200,
        )
        
        with pytest.raises(LinearError, match="Linear API errors"):
            client.get_teams()
    
    @responses.activate
    def test_search_issues(self, monkeypatch):
        """Test searching for issues."""
        monkeypatch.setenv("LINEAR_API_KEY", "test-key")
        client = LinearClient()
        
        # Mock API response
        responses.add(
            responses.POST,
            "https://api.linear.app/graphql",
            json={
                "data": {
                    "issues": {
                        "nodes": [
                            {
                                "id": "issue-1",
                                "identifier": "ENG-1",
                                "title": "Test Issue",
                                "description": "Test description",
                                "state": {
                                    "name": "Todo",
                                    "type": "started",
                                },
                                "assignee": None,
                                "creator": None,
                                "createdAt": "2024-01-01T00:00:00Z",
                                "updatedAt": "2024-01-01T00:00:00Z",
                                "url": "https://linear.app/test/ENG-1",
                                "priority": 1,
                                "labels": {
                                    "nodes": [],
                                },
                            }
                        ]
                    }
                }
            },
            status=200,
        )
        
        issues = client.search_issues(query="test", limit=10)
        assert len(issues) == 1
        assert issues[0]["id"] == "issue-1"
        assert issues[0]["title"] == "Test Issue"
    
    @responses.activate
    def test_create_issue(self, monkeypatch):
        """Test creating an issue."""
        monkeypatch.setenv("LINEAR_API_KEY", "test-key")
        client = LinearClient()
        
        # Mock API response
        responses.add(
            responses.POST,
            "https://api.linear.app/graphql",
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {
                            "id": "issue-1",
                            "identifier": "ENG-1",
                            "title": "New Issue",
                            "description": "Description",
                            "state": {
                                "name": "Todo",
                                "type": "started",
                            },
                            "assignee": None,
                            "creator": None,
                            "createdAt": "2024-01-01T00:00:00Z",
                            "url": "https://linear.app/test/ENG-1",
                            "priority": 1,
                        },
                    }
                }
            },
            status=200,
        )
        
        issue = client.create_issue(
            team_id="team-1",
            title="New Issue",
            description="Description",
        )
        assert issue["id"] == "issue-1"
        assert issue["title"] == "New Issue"


