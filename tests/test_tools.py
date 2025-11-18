"""Tests for tools."""
import pytest
from unittest.mock import patch, Mock

from tools import (
    get_code_context_tool,
    get_history_context_tool,
    search_linear_issues_tool,
    create_linear_issue_tool,
    get_linear_issues_for_block_tool,
    GetCodeContextInput,
    GetHistoryContextInput,
    SearchLinearIssuesInput,
    CreateLinearIssueInput,
    GetLinearIssuesForBlockInput,
)
from models import BlockRef


class TestGitTools:
    """Tests for git-related tools."""
    
    @patch("tools.get_code_context")
    def test_get_code_context_tool(self, mock_get_code_context, mock_block_ref):
        """Test get_code_context_tool."""
        from models import CodeContext
        
        # Mock the git_core function
        mock_get_code_context.return_value = CodeContext(
            block_ref=mock_block_ref,
            code_block="def test(): pass",
            surrounding_code="import os\n\ndef test(): pass",
            context_start_line=1,
            context_end_line=10,
            file_total_lines=10,
            language="python",
        )
        
        result = get_code_context_tool(
            GetCodeContextInput(block_ref=mock_block_ref, context_lines=10)
        )
        
        assert result.code_block == "def test(): pass"
        assert result.language == "python"
        mock_get_code_context.assert_called_once()
    
    @patch("tools.build_history_context")
    def test_get_history_context_tool(self, mock_build_history, mock_block_ref):
        """Test get_history_context_tool."""
        from models import HistoryContext
        
        # Mock the git_core function
        mock_build_history.return_value = HistoryContext(
            block_ref=mock_block_ref,
            blame=None,
            commits=[],
            prs=[],
        )
        
        result = get_history_context_tool(
            GetHistoryContextInput(block_ref=mock_block_ref, max_commits=10)
        )
        
        assert result.block_ref == mock_block_ref
        mock_build_history.assert_called_once()


class TestLinearTools:
    """Tests for Linear-related tools."""
    
    @patch("tools.LinearClient")
    def test_search_linear_issues_tool_success(self, mock_linear_client_class, mock_linear_issue):
        """Test searching Linear issues successfully."""
        mock_client = Mock()
        mock_linear_client_class.return_value = mock_client
        mock_client.search_issues.return_value = [
            {
                "id": "issue-1",
                "identifier": "ENG-1",
                "title": "Test Issue",
                "description": "Test",
                "state": {"name": "Todo", "type": "started"},
                "assignee": None,
                "creator": None,
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
                "url": "https://linear.app/test/ENG-1",
                "priority": 1,
                "labels": {"nodes": []},
            }
        ]
        
        result = search_linear_issues_tool(
            SearchLinearIssuesInput(query="test", limit=10)
        )
        
        assert len(result) == 1
        assert result[0].identifier == "ENG-1"
    
    @patch("tools.LinearClient")
    def test_search_linear_issues_tool_error(self, mock_linear_client_class):
        """Test searching Linear issues with error."""
        from linear_client import LinearError
        
        mock_client = Mock()
        mock_linear_client_class.return_value = mock_client
        mock_client.search_issues.side_effect = LinearError("API error")
        
        # Should return empty list on error
        result = search_linear_issues_tool(
            SearchLinearIssuesInput(query="test", limit=10)
        )
        
        assert result == []
    
    @patch("tools.LinearClient")
    def test_create_linear_issue_tool(self, mock_linear_client_class):
        """Test creating a Linear issue."""
        mock_client = Mock()
        mock_linear_client_class.return_value = mock_client
        mock_client.create_issue.return_value = {
            "id": "issue-1",
            "identifier": "ENG-1",
            "title": "New Issue",
            "description": "Description",
            "state": {"name": "Todo", "type": "started"},
            "assignee": None,
            "creator": None,
            "createdAt": "2024-01-01T00:00:00Z",
            "url": "https://linear.app/test/ENG-1",
            "priority": 1,
            "labels": {"nodes": []},
        }
        
        result = create_linear_issue_tool(
            CreateLinearIssueInput(
                team_id="team-1",
                title="New Issue",
                description="Description",
            )
        )
        
        assert result.identifier == "ENG-1"
        assert result.title == "New Issue"
        mock_client.create_issue.assert_called_once()
    
    @patch("tools.LinearClient")
    def test_get_linear_issues_for_block_tool(self, mock_linear_client_class, mock_block_ref):
        """Test getting Linear issues for a code block."""
        mock_client = Mock()
        mock_linear_client_class.return_value = mock_client
        mock_client.search_issues.return_value = [
            {
                "id": "issue-1",
                "identifier": "ENG-1",
                "title": "Related Issue",
                "description": "Test",
                "state": {"name": "Todo", "type": "started"},
                "assignee": None,
                "creator": None,
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-01T00:00:00Z",
                "url": "https://linear.app/test/ENG-1",
                "priority": 1,
                "labels": {"nodes": []},
            }
        ]
        
        result = get_linear_issues_for_block_tool(
            GetLinearIssuesForBlockInput(block_ref=mock_block_ref, limit=10)
        )
        
        assert result.block_ref == mock_block_ref
        assert len(result.issues) == 1
        assert result.issues[0].identifier == "ENG-1"


