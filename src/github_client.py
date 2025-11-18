from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

# GitHub API endpoint
GITHUB_API_URL = "https://api.github.com"


class GitHubError(RuntimeError):
    """Exception raised for GitHub API errors."""
    pass


class GitHubClient:
    """Client for interacting with GitHub's REST API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the GitHub client.

        Args:
            api_key: GitHub API key (Personal Access Token). If not provided,
                will try to get from GITHUB_API_KEY environment variable.
                Note: API key is optional for public repositories, but recommended
                for higher rate limits (5,000 vs 60 requests/hour).
        """
        self.api_key = api_key or os.getenv("GITHUB_API_KEY")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "git-history-agent",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a request to the GitHub API.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint (e.g., '/repos/owner/repo/pulls').
            params: Optional query parameters.

        Returns:
            Dict[str, Any]: Response data from the API.

        Raises:
            GitHubError: If the API request fails or returns errors.
        """
        url = f"{GITHUB_API_URL}{endpoint}"
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise GitHubError(f"Repository or resource not found: {endpoint}")
            elif e.response.status_code == 403:
                raise GitHubError(
                    f"GitHub API rate limit exceeded or access denied: {e.response.text}"
                )
            else:
                raise GitHubError(f"GitHub API error ({e.response.status_code}): {e.response.text}")
        except httpx.HTTPError as e:
            raise GitHubError(f"HTTP error while calling GitHub API: {e}")
        except Exception as e:
            raise GitHubError(f"Unexpected error calling GitHub API: {e}")

    def get_prs_for_commits(
        self,
        owner: str,
        repo: str,
        commit_shas: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get PRs associated with commit SHAs.

        Uses GitHub's search API to find PRs that contain each commit SHA.
        GitHub Search API: q=repo:owner/repo+sha:commit_sha+type:pr

        Args:
            owner: Repository owner (username or organization).
            repo: Repository name.
            commit_shas: List of commit SHA strings.

        Returns:
            Dict[str, List[Dict[str, Any]]]: Dictionary mapping commit SHA to list of PRs.
        """
        commit_to_prs: Dict[str, List[Dict[str, Any]]] = {sha: [] for sha in commit_shas}
        
        # For each commit, search for PRs that contain it
        for sha in commit_shas:
            try:
                # Use GitHub's search API to find PRs with this commit
                # Format: q=repo:owner/repo+sha:commit_sha+type:pr
                query = f"repo:{owner}/{repo} sha:{sha} type:pr"
                endpoint = "/search/issues"
                params = {"q": query, "per_page": 10}
                
                response = self._make_request("GET", endpoint, params=params)
                items = response.get("items", [])
                
                # Get full PR details for each found PR
                seen_pr_numbers: set[int] = set()
                for item in items:
                    pr_number = item.get("number")
                    if pr_number and pr_number not in seen_pr_numbers:
                        try:
                            pr_details = self.get_pull_request(owner, repo, pr_number)
                            commit_to_prs[sha].append(pr_details)
                            seen_pr_numbers.add(pr_number)
                        except GitHubError:
                            # If we can't get PR details, skip it
                            continue
            except GitHubError:
                # If search fails, continue with next commit
                # This is expected for commits that aren't in any PR
                continue
        
        return commit_to_prs

    def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> Dict[str, Any]:
        """Get a specific pull request by number.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: Pull request number.

        Returns:
            Dict[str, Any]: Pull request data.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
        return self._make_request("GET", endpoint)

    def get_pr_reviews(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> List[Dict[str, Any]]:
        """Get reviews for a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: Pull request number.

        Returns:
            List[Dict[str, Any]]: List of review data.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        return self._make_request("GET", endpoint)

    def get_pr_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> List[Dict[str, Any]]:
        """Get comments for a pull request.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: Pull request number.

        Returns:
            List[Dict[str, Any]]: List of comment data.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        return self._make_request("GET", endpoint)

    def get_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
    ) -> List[Dict[str, Any]]:
        """Get comments for an issue (PRs are also issues in GitHub).

        Args:
            owner: Repository owner.
            repo: Repository name.
            issue_number: Issue/PR number.

        Returns:
            List[Dict[str, Any]]: List of comment data.
        """
        endpoint = f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
        return self._make_request("GET", endpoint)

    def get_pr_discussion(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        include_reviews: bool = True,
        include_comments: bool = True,
        max_comments: int = 50,
    ) -> Dict[str, Any]:
        """Get complete PR discussion including reviews and comments.

        Args:
            owner: Repository owner.
            repo: Repository name.
            pr_number: Pull request number.
            include_reviews: Whether to include review comments.
            include_comments: Whether to include issue comments.
            max_comments: Maximum number of comments to include.

        Returns:
            Dict[str, Any]: PR discussion data with reviews and comments.
        """
        # Get PR details
        pr = self.get_pull_request(owner, repo, pr_number)
        
        discussion = {
            "pr": pr,
            "reviews": [],
            "review_comments": [],
            "issue_comments": [],
        }
        
        if include_reviews:
            try:
                reviews = self.get_pr_reviews(owner, repo, pr_number)
                discussion["reviews"] = reviews[:max_comments]
            except GitHubError:
                pass
        
        if include_comments:
            try:
                # Get review comments (comments on code)
                review_comments = self.get_pr_comments(owner, repo, pr_number)
                discussion["review_comments"] = review_comments[:max_comments]
            except GitHubError:
                pass
            
            try:
                # Get issue comments (general PR comments)
                issue_comments = self.get_issue_comments(owner, repo, pr_number)
                discussion["issue_comments"] = issue_comments[:max_comments]
            except GitHubError:
                pass
        
        return discussion

    def search_prs(
        self,
        owner: str,
        repo: str,
        query: Optional[str] = None,
        state: str = "all",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for pull requests in a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            query: Optional search query.
            state: PR state ('open', 'closed', 'all').
            limit: Maximum number of PRs to return.

        Returns:
            List[Dict[str, Any]]: List of PR data.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls"
        params = {
            "state": state,
            "per_page": min(limit, 100),  # GitHub API max is 100
            "sort": "updated",
            "direction": "desc",
        }
        
        if query:
            # If query is provided, use search API instead
            search_query = f"repo:{owner}/{repo} type:pr {query}"
            if state != "all":
                search_query += f" state:{state}"
            
            endpoint = "/search/issues"
            params = {"q": search_query, "per_page": min(limit, 100)}
            response = self._make_request("GET", endpoint, params=params)
            return response.get("items", [])
        
        return self._make_request("GET", endpoint, params=params)


__all__ = ["GitHubClient", "GitHubError", "GITHUB_API_URL"]

