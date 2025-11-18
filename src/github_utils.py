"""Utility functions for converting GitHub API responses to our models."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from models import PRDiscussionSummary


def github_pr_to_pr_summary(
    pr_data: Dict[str, Any],
    discussion_data: Optional[Dict[str, Any]] = None,
    max_comments: int = 10,
) -> PRDiscussionSummary:
    """Convert GitHub PR API response to PRDiscussionSummary model.

    Args:
        pr_data: GitHub PR API response data.
        discussion_data: Optional discussion data including reviews and comments.
        max_comments: Maximum number of key comments to include.

    Returns:
        PRDiscussionSummary: Converted PR discussion summary.
    """
    # Extract PR basic info
    number = pr_data.get("number", 0)
    title = pr_data.get("title", "")
    url = pr_data.get("html_url", pr_data.get("url", ""))
    state = pr_data.get("state", "unknown")
    merged_at = pr_data.get("merged_at")
    
    # Extract PR body as summary
    body = pr_data.get("body", "")
    summary = body[:500] if body else "No description provided."  # Limit summary length
    
    # Extract key comments from discussion data
    key_comments: List[str] = []
    
    if discussion_data:
        # Add review comments (comments on code)
        review_comments = discussion_data.get("review_comments", [])
        for comment in review_comments[:max_comments // 2]:
            comment_body = comment.get("body", "")
            if comment_body:
                # Include comment with author and context
                author = comment.get("user", {}).get("login", "Unknown")
                key_comments.append(f"[@{author}] {comment_body[:200]}")
        
        # Add issue comments (general PR comments)
        issue_comments = discussion_data.get("issue_comments", [])
        for comment in issue_comments[:max_comments // 2]:
            comment_body = comment.get("body", "")
            if comment_body:
                author = comment.get("user", {}).get("login", "Unknown")
                key_comments.append(f"[@{author}] {comment_body[:200]}")
        
        # Add review summaries
        reviews = discussion_data.get("reviews", [])
        for review in reviews[:5]:  # Limit to 5 reviews
            review_body = review.get("body", "")
            review_state = review.get("state", "")
            if review_body:
                author = review.get("user", {}).get("login", "Unknown")
                key_comments.append(f"[Review @{author} - {review_state}] {review_body[:200]}")
    
    return PRDiscussionSummary(
        number=number,
        title=title,
        url=url,
        state=state,
        merged_at=merged_at,
        summary=summary,
        key_comments=key_comments[:max_comments],
    )


def extract_pr_numbers_from_commits(
    commit_to_prs: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, List[int]]:
    """Extract PR numbers from commit-to-PR mapping.

    Args:
        commit_to_prs: Dictionary mapping commit SHA to list of PR data.

    Returns:
        Dict[str, List[int]]: Dictionary mapping commit SHA to list of PR numbers.
    """
    commit_to_pr_numbers: Dict[str, List[int]] = {}
    
    for sha, prs in commit_to_prs.items():
        pr_numbers = [pr.get("number") for pr in prs if pr.get("number")]
        commit_to_pr_numbers[sha] = pr_numbers
    
    return commit_to_pr_numbers


def get_unique_prs(
    commit_to_prs: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Get unique PRs from commit-to-PR mapping.

    Args:
        commit_to_prs: Dictionary mapping commit SHA to list of PR data.

    Returns:
        List[Dict[str, Any]]: List of unique PR data dictionaries.
    """
    seen_pr_numbers: set[int] = set()
    unique_prs: List[Dict[str, Any]] = []
    
    for prs in commit_to_prs.values():
        for pr in prs:
            pr_number = pr.get("number")
            if pr_number and pr_number not in seen_pr_numbers:
                seen_pr_numbers.add(pr_number)
                unique_prs.append(pr)
    
    return unique_prs


__all__ = [
    "github_pr_to_pr_summary",
    "extract_pr_numbers_from_commits",
    "get_unique_prs",
]


