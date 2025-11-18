"""Tests for GitHub client."""
import pytest
import responses

from github_client import GitHubClient, GitHubError


class TestGitHubClient:
    """Tests for GitHubClient."""
    
    def test_github_client_init_without_key(self, monkeypatch):
        """Test GitHubClient initialization without API key."""
        monkeypatch.delenv("GITHUB_API_KEY", raising=False)
        # GitHub client should work without API key for public repos
        client = GitHubClient()
        assert client.api_key is None
        assert "Authorization" not in client.headers
    
    def test_github_client_init_with_key(self, monkeypatch):
        """Test GitHubClient initialization with API key."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        assert client.api_key == "test-key"
        assert "Bearer test-key" in client.headers["Authorization"]
    
    @responses.activate
    def test_get_pull_request_success(self, monkeypatch):
        """Test getting a pull request successfully."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        
        # Mock API response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/123",
            json={
                "number": 123,
                "title": "Test PR",
                "body": "Test PR description",
                "state": "closed",
                "merged_at": "2024-01-01T00:00:00Z",
                "html_url": "https://github.com/test-owner/test-repo/pull/123",
            },
            status=200,
        )
        
        pr = client.get_pull_request("test-owner", "test-repo", 123)
        assert pr["number"] == 123
        assert pr["title"] == "Test PR"
    
    @responses.activate
    def test_get_prs_for_commits(self, monkeypatch):
        """Test getting PRs for commits."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        
        # Mock search API response
        responses.add(
            responses.GET,
            "https://api.github.com/search/issues",
            json={
                "items": [
                    {
                        "number": 123,
                        "title": "Test PR",
                    }
                ]
            },
            status=200,
        )
        
        # Mock PR details response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/123",
            json={
                "number": 123,
                "title": "Test PR",
                "body": "Test description",
                "state": "closed",
                "html_url": "https://github.com/test-owner/test-repo/pull/123",
            },
            status=200,
        )
        
        commit_to_prs = client.get_prs_for_commits(
            owner="test-owner",
            repo="test-repo",
            commit_shas=["abc123"],
        )
        
        assert "abc123" in commit_to_prs
        assert len(commit_to_prs["abc123"]) == 1
        assert commit_to_prs["abc123"][0]["number"] == 123
    
    @responses.activate
    def test_get_pr_discussion(self, monkeypatch):
        """Test getting PR discussion."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        
        # Mock PR response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/123",
            json={
                "number": 123,
                "title": "Test PR",
                "body": "Test description",
                "state": "closed",
            },
            status=200,
        )
        
        # Mock reviews response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/123/reviews",
            json=[
                {
                    "id": 1,
                    "body": "Looks good!",
                    "state": "APPROVED",
                    "user": {"login": "reviewer"},
                }
            ],
            status=200,
        )
        
        # Mock comments response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/123/comments",
            json=[
                {
                    "id": 1,
                    "body": "Nice work!",
                    "user": {"login": "commenter"},
                }
            ],
            status=200,
        )
        
        # Mock issue comments response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/issues/123/comments",
            json=[
                {
                    "id": 1,
                    "body": "Great PR!",
                    "user": {"login": "commenter"},
                }
            ],
            status=200,
        )
        
        discussion = client.get_pr_discussion(
            owner="test-owner",
            repo="test-repo",
            pr_number=123,
        )
        
        assert discussion["pr"]["number"] == 123
        assert len(discussion["reviews"]) == 1
        assert len(discussion["review_comments"]) == 1
        assert len(discussion["issue_comments"]) == 1
    
    @responses.activate
    def test_search_prs(self, monkeypatch):
        """Test searching for PRs."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        
        # Mock API response
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls",
            json=[
                {
                    "number": 123,
                    "title": "Test PR",
                    "state": "open",
                }
            ],
            status=200,
        )
        
        prs = client.search_prs(
            owner="test-owner",
            repo="test-repo",
            state="open",
            limit=10,
        )
        
        assert len(prs) == 1
        assert prs[0]["number"] == 123
    
    @responses.activate
    def test_api_error_handling(self, monkeypatch):
        """Test API error handling."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        
        # Mock 404 error
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/999",
            status=404,
        )
        
        with pytest.raises(GitHubError, match="not found"):
            client.get_pull_request("test-owner", "test-repo", 999)
    
    @responses.activate
    def test_rate_limit_error(self, monkeypatch):
        """Test rate limit error handling."""
        monkeypatch.setenv("GITHUB_API_KEY", "test-key")
        client = GitHubClient()
        
        # Mock 403 error (rate limit)
        responses.add(
            responses.GET,
            "https://api.github.com/repos/test-owner/test-repo/pulls/123",
            status=403,
            json={"message": "API rate limit exceeded"},
        )
        
        with pytest.raises(GitHubError, match="rate limit"):
            client.get_pull_request("test-owner", "test-repo", 123)


class TestGitHubUtils:
    """Tests for GitHub utility functions."""
    
    def test_github_pr_to_pr_summary(self):
        """Test converting GitHub PR to PRDiscussionSummary."""
        from github_utils import github_pr_to_pr_summary
        from models import PRDiscussionSummary
        
        pr_data = {
            "number": 123,
            "title": "Test PR",
            "body": "Test description",
            "state": "closed",
            "merged_at": "2024-01-01T00:00:00Z",
            "html_url": "https://github.com/test/test/pull/123",
        }
        
        discussion_data = {
            "review_comments": [
                {
                    "body": "Looks good!",
                    "user": {"login": "reviewer"},
                }
            ],
            "issue_comments": [
                {
                    "body": "Great work!",
                    "user": {"login": "commenter"},
                }
            ],
            "reviews": [
                {
                    "body": "Approved",
                    "state": "APPROVED",
                    "user": {"login": "reviewer"},
                }
            ],
        }
        
        pr_summary = github_pr_to_pr_summary(pr_data, discussion_data)
        
        assert isinstance(pr_summary, PRDiscussionSummary)
        assert pr_summary.number == 123
        assert pr_summary.title == "Test PR"
        assert pr_summary.state == "closed"
        assert len(pr_summary.key_comments) > 0
    
    def test_extract_pr_numbers_from_commits(self):
        """Test extracting PR numbers from commit-to-PR mapping."""
        from github_utils import extract_pr_numbers_from_commits
        
        commit_to_prs = {
            "abc123": [
                {"number": 123},
                {"number": 124},
            ],
            "def456": [
                {"number": 125},
            ],
        }
        
        result = extract_pr_numbers_from_commits(commit_to_prs)
        
        assert result["abc123"] == [123, 124]
        assert result["def456"] == [125]
    
    def test_get_unique_prs(self):
        """Test getting unique PRs."""
        from github_utils import get_unique_prs
        
        commit_to_prs = {
            "abc123": [
                {"number": 123, "title": "PR 123"},
            ],
            "def456": [
                {"number": 123, "title": "PR 123"},  # Duplicate
                {"number": 124, "title": "PR 124"},
            ],
        }
        
        unique_prs = get_unique_prs(commit_to_prs)
        
        # Should only have 2 unique PRs
        assert len(unique_prs) == 2
        pr_numbers = [pr["number"] for pr in unique_prs]
        assert 123 in pr_numbers
        assert 124 in pr_numbers

