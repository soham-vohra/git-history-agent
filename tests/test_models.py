"""Tests for models."""
import pytest

from models import (
    BlockRef,
    CodeContext,
    HistoryContext,
    LinearIssue,
    LinearTeam,
    CommitSummary,
    BlameEntry,
    BlameBlock,
)


class TestBlockRef:
    """Tests for BlockRef model."""
    
    def test_block_ref_creation(self):
        """Test creating a BlockRef."""
        block_ref = BlockRef(
            repo_owner="test-owner",
            repo_name="test-repo",
            ref="main",
            path="src/test.py",
            start_line=10,
            end_line=20,
        )
        assert block_ref.repo_owner == "test-owner"
        assert block_ref.repo_name == "test-repo"
        assert block_ref.ref == "main"
        assert block_ref.path == "src/test.py"
        assert block_ref.start_line == 10
        assert block_ref.end_line == 20
    
    def test_block_ref_validation(self):
        """Test BlockRef validation."""
        # Should raise error for invalid line numbers
        with pytest.raises(Exception):
            BlockRef(
                repo_owner="test",
                repo_name="test",
                ref="main",
                path="test.py",
                start_line=0,  # Invalid: must be >= 1
                end_line=10,
            )
    
    def test_block_ref_to_dict(self):
        """Test BlockRef to_dict method."""
        block_ref = BlockRef(
            repo_owner="test",
            repo_name="test",
            ref="main",
            path="test.py",
            start_line=1,
            end_line=10,
        )
        result = block_ref.to_dict()
        assert isinstance(result, dict)
        assert result["repo_owner"] == "test"
        assert result["start_line"] == 1


class TestCodeContext:
    """Tests for CodeContext model."""
    
    def test_code_context_creation(self, mock_block_ref):
        """Test creating a CodeContext."""
        context = CodeContext(
            block_ref=mock_block_ref,
            code_block="def test():\n    pass",
            surrounding_code="import os\n\ndef test():\n    pass",
            context_start_line=1,
            context_end_line=10,
            file_total_lines=10,
            language="python",
        )
        assert context.code_block == "def test():\n    pass"
        assert context.language == "python"
        assert context.file_total_lines == 10


class TestLinearModels:
    """Tests for Linear models."""
    
    def test_linear_issue_creation(self):
        """Test creating a LinearIssue."""
        from models import LinearIssueState, LinearUser
        
        issue = LinearIssue(
            id="test-id",
            identifier="TEST-1",
            title="Test Issue",
            description="Test description",
            state=LinearIssueState(name="Todo", type="started"),
            assignee=LinearUser(name="Test User", email="test@example.com"),
            url="https://linear.app/test/TEST-1",
            priority=1,
        )
        assert issue.id == "test-id"
        assert issue.identifier == "TEST-1"
        assert issue.title == "Test Issue"
        assert issue.priority == 1
    
    def test_linear_team_creation(self):
        """Test creating a LinearTeam."""
        team = LinearTeam(
            id="team-1",
            key="ENG",
            name="Engineering",
        )
        assert team.id == "team-1"
        assert team.key == "ENG"
        assert team.name == "Engineering"


class TestHistoryContext:
    """Tests for HistoryContext model."""
    
    def test_history_context_creation(self, mock_block_ref):
        """Test creating a HistoryContext."""
        context = HistoryContext(
            block_ref=mock_block_ref,
            blame=None,
            commits=[],
            prs=[],
        )
        assert context.block_ref == mock_block_ref
        assert context.commits == []
        assert context.prs == []


