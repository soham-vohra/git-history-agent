"""Pytest configuration and shared fixtures."""
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()


@pytest.fixture
def mock_block_ref():
    """Create a mock BlockRef for testing."""
    from models import BlockRef
    
    return BlockRef(
        repo_owner="test-owner",
        repo_name="test-repo",
        ref="main",
        path="src/test.py",
        start_line=10,
        end_line=20,
    )


@pytest.fixture
def mock_code_context(mock_block_ref):
    """Create a mock CodeContext for testing."""
    from models import CodeContext
    
    return CodeContext(
        block_ref=mock_block_ref,
        code_block="def test_function():\n    return True",
        surrounding_code="import os\n\ndef test_function():\n    return True\n\nif __name__ == '__main__':\n    pass",
        context_start_line=1,
        context_end_line=10,
        file_total_lines=10,
        language="python",
    )


@pytest.fixture
def mock_history_context(mock_block_ref):
    """Create a mock HistoryContext for testing."""
    from models import HistoryContext, CommitSummary, BlameBlock, BlameEntry
    
    commits = [
        CommitSummary(
            sha="abc123",
            author="Test Author",
            author_email="test@example.com",
            date="2024-01-01",
            message="Test commit",
            diff_hunks_for_block=["+def test_function():"],
        )
    ]
    
    blame_entries = [
        BlameEntry(
            block_ref=mock_block_ref,
            line=10,
            code="def test_function():",
            commit="abc123",
            author="Test Author",
            author_email="test@example.com",
            author_time="2024-01-01",
            summary="Test commit",
        )
    ]
    
    blame_block = BlameBlock(
        block_ref=mock_block_ref,
        entries=blame_entries,
    )
    
    return HistoryContext(
        block_ref=mock_block_ref,
        blame=blame_block,
        commits=commits,
        prs=[],
    )


@pytest.fixture
def mock_linear_issue():
    """Create a mock Linear issue for testing."""
    from models import LinearIssue, LinearIssueState, LinearUser
    
    return LinearIssue(
        id="test-issue-id",
        identifier="TEST-1",
        title="Test Issue",
        description="Test description",
        state=LinearIssueState(name="Todo", type="started"),
        assignee=LinearUser(name="Test User", email="test@example.com"),
        creator=LinearUser(name="Creator", email="creator@example.com"),
        createdAt="2024-01-01T00:00:00Z",
        updatedAt="2024-01-01T00:00:00Z",
        url="https://linear.app/test/TEST-1",
        priority=1,
        labels=[],
    )


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    with patch("openai.OpenAI") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        
        # Mock chat completion response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].message.tool_calls = None
        
        mock_instance.chat.completions.create.return_value = mock_response
        
        yield mock_instance


@pytest.fixture
def mock_gemini_client():
    """Mock Gemini client for testing."""
    with patch("google.generativeai.GenerativeModel") as mock_model:
        mock_instance = Mock()
        mock_model.return_value = mock_instance
        
        mock_response = Mock()
        mock_response.text = "Test Gemini response"
        mock_instance.generate_content.return_value = mock_response
        
        yield mock_instance


@pytest.fixture
def mock_linear_api_response():
    """Mock Linear API response."""
    return {
        "data": {
            "teams": {
                "nodes": [
                    {
                        "id": "team-1",
                        "key": "ENG",
                        "name": "Engineering",
                    }
                ]
            },
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
                        "assignee": {
                            "name": "Test User",
                            "email": "test@example.com",
                        },
                        "creator": {
                            "name": "Creator",
                            "email": "creator@example.com",
                        },
                        "createdAt": "2024-01-01T00:00:00Z",
                        "updatedAt": "2024-01-01T00:00:00Z",
                        "url": "https://linear.app/test/ENG-1",
                        "priority": 1,
                        "labels": {
                            "nodes": [],
                        },
                    }
                ]
            },
        }
    }


@pytest.fixture
def test_env_vars(monkeypatch):
    """Set test environment variables."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("LINEAR_API_KEY", "test-linear-key")
    monkeypatch.setenv("REPOS_ROOT", str(Path(__file__).parent / "test_repos"))
    monkeypatch.setenv("LLM_PROVIDER", "openai")


@pytest.fixture
def test_repo_path(tmp_path):
    """Create a test git repository."""
    import subprocess
    
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    
    # Create a test file
    test_file = repo_path / "test.py"
    test_file.write_text("def test_function():\n    return True\n")
    
    # Commit the file
    subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    
    return repo_path


