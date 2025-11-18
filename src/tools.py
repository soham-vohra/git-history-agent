from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field

from models import (
    BlockRef,
    CodeContext,
    HistoryContext,
    LinearIssue,
    LinearIssueContext,
    LinearTeam,
    LinearIssueState,
    LinearUser,
    LinearLabel,
)
from git_core import get_code_context, build_history_context
from linear_client import LinearClient, LinearError


class GetCodeContextInput(BaseModel):
    """Input model for the get_code_context tool.

    Attributes:
        block_ref: BlockRef specifying the code block to retrieve.
        context_lines: Number of lines to include above and below the block
            for context (default: 10).
    """
    block_ref: BlockRef
    context_lines: int = Field(10, ge=0) # +/- how many lines we want to pull in for context


class GetHistoryContextInput(BaseModel):
    """Input model for the get_history_context tool.

    Attributes:
        block_ref: BlockRef specifying the code block to analyze.
        max_commits: Maximum number of distinct commits to retrieve
            (default: 10, minimum: 1).
    """
    block_ref: BlockRef
    max_commits: int = Field(10, ge=1)


def get_code_context_tool(params: GetCodeContextInput) -> CodeContext:
    """Wrapper function for getting code context, designed for LLM tool calling.

    Retrieves a code block with surrounding context lines from a git repository.
    This function wraps the core get_code_context function to provide a clean
    interface for LLM tool execution.

    Args:
        params: GetCodeContextInput containing the block reference and
            context line count.

    Returns:
        CodeContext: A model containing the code block, surrounding code,
            line numbers, total file lines, and detected language.

    Raises:
        GitError: If the line range is invalid or the file cannot be read.
    """
    return get_code_context(
        block_ref=params.block_ref,
        context_lines=params.context_lines,
    )


def get_history_context_tool(params: GetHistoryContextInput) -> HistoryContext:
    """Wrapper function for getting history context, designed for LLM tool calling.

    Retrieves git blame information and commit history for a code block.
    This function wraps the core build_history_context function to provide
    a clean interface for LLM tool execution. Also fetches PR discussions
    from GitHub if available.

    Args:
        params: GetHistoryContextInput containing the block reference and
            maximum commit count.

    Returns:
        HistoryContext: A model containing blame information, commit summaries,
            and PR discussions from GitHub.
    """
    return build_history_context(
        block_ref=params.block_ref,
        max_commits=params.max_commits,
        include_prs=True,  # Enable PR fetching by default
        max_prs=10,  # Limit to 10 PRs
    )


class SearchLinearIssuesInput(BaseModel):
    """Input model for the search_linear_issues tool.

    Attributes:
        query: Optional search query string (searches title and description).
        team_id: Optional team ID to filter by.
        state: Optional state name to filter by.
        limit: Maximum number of issues to return (default: 20).
    """
    query: Optional[str] = None
    team_id: Optional[str] = None
    state: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)


class CreateLinearIssueInput(BaseModel):
    """Input model for the create_linear_issue tool.

    Attributes:
        team_id: ID of the team to create the issue in.
        title: Issue title.
        description: Optional issue description.
        assignee_id: Optional assignee ID.
        state_id: Optional state ID.
        priority: Optional priority (0-4, where 0 is urgent, 4 is none).
        label_ids: Optional list of label IDs.
    """
    team_id: str
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    state_id: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=4)
    label_ids: Optional[List[str]] = None


class GetLinearIssuesForBlockInput(BaseModel):
    """Input model for the get_linear_issues_for_block tool.

    Attributes:
        block_ref: BlockRef specifying the code block to search for.
        team_id: Optional team ID to filter by.
        limit: Maximum number of issues to return (default: 10).
    """
    block_ref: BlockRef
    team_id: Optional[str] = None
    limit: int = Field(10, ge=1, le=50)


def _dict_to_linear_issue(issue_dict: dict) -> LinearIssue:
    """Convert a dictionary from Linear API to a LinearIssue model.

    Args:
        issue_dict: Dictionary from Linear API response.

    Returns:
        LinearIssue: Parsed LinearIssue model.
    """
    state = None
    if issue_dict.get("state"):
        state = LinearIssueState(
            name=issue_dict["state"].get("name", ""),
            type=issue_dict["state"].get("type", ""),
        )

    assignee = None
    if issue_dict.get("assignee"):
        assignee = LinearUser(
            name=issue_dict["assignee"].get("name"),
            email=issue_dict["assignee"].get("email"),
        )

    creator = None
    if issue_dict.get("creator"):
        creator = LinearUser(
            name=issue_dict["creator"].get("name"),
            email=issue_dict["creator"].get("email"),
        )

    labels = []
    if issue_dict.get("labels") and issue_dict["labels"].get("nodes"):
        labels = [
            LinearLabel(id=label.get("id", ""), name=label.get("name", ""))
            for label in issue_dict["labels"]["nodes"]
        ]

    return LinearIssue(
        id=issue_dict.get("id", ""),
        identifier=issue_dict.get("identifier", ""),
        title=issue_dict.get("title", ""),
        description=issue_dict.get("description"),
        state=state,
        assignee=assignee,
        creator=creator,
        createdAt=issue_dict.get("createdAt"),
        updatedAt=issue_dict.get("updatedAt"),
        url=issue_dict.get("url"),
        priority=issue_dict.get("priority"),
        labels=labels,
    )


def search_linear_issues_tool(params: SearchLinearIssuesInput) -> List[LinearIssue]:
    """Wrapper function for searching Linear issues, designed for LLM tool calling.

    Searches for issues in Linear based on query, team, and state filters.

    Args:
        params: SearchLinearIssuesInput containing search parameters.

    Returns:
        List[LinearIssue]: List of matching Linear issues.

    Raises:
        LinearError: If the Linear API call fails.
    """
    try:
        client = LinearClient()
        issues_dict = client.search_issues(
            query=params.query,
            team_id=params.team_id,
            state=params.state,
            limit=params.limit,
        )
        return [_dict_to_linear_issue(issue) for issue in issues_dict]
    except LinearError:
        # If Linear is not configured, return empty list
        return []


def create_linear_issue_tool(params: CreateLinearIssueInput) -> LinearIssue:
    """Wrapper function for creating a Linear issue, designed for LLM tool calling.

    Creates a new issue in Linear.

    Args:
        params: CreateLinearIssueInput containing issue details.

    Returns:
        LinearIssue: Created Linear issue.

    Raises:
        LinearError: If the Linear API call fails.
    """
    client = LinearClient()
    issue_dict = client.create_issue(
        team_id=params.team_id,
        title=params.title,
        description=params.description,
        assignee_id=params.assignee_id,
        state_id=params.state_id,
        priority=params.priority,
        label_ids=params.label_ids,
    )
    return _dict_to_linear_issue(issue_dict)


def get_linear_issues_for_block_tool(params: GetLinearIssuesForBlockInput) -> LinearIssueContext:
    """Wrapper function for finding Linear issues related to a code block.

    Searches for Linear issues that might be related to a code block by searching
    for the file path, repository name, or line numbers in issue descriptions.

    Args:
        params: GetLinearIssuesForBlockInput containing block reference and filters.

    Returns:
        LinearIssueContext: Context containing related Linear issues.

    Raises:
        LinearError: If the Linear API call fails.
    """
    try:
        client = LinearClient()
        # Build search query from block reference
        search_terms = [
            params.block_ref.repo_name,
            params.block_ref.path,
            f"{params.block_ref.path}:{params.block_ref.start_line}-{params.block_ref.end_line}",
        ]
        query = " OR ".join(search_terms)

        issues_dict = client.search_issues(
            query=query,
            team_id=params.team_id,
            limit=params.limit,
        )
        issues = [_dict_to_linear_issue(issue) for issue in issues_dict]

        return LinearIssueContext(
            block_ref=params.block_ref,
            issues=issues,
        )
    except LinearError:
        # If Linear is not configured, return empty context
        return LinearIssueContext(
            block_ref=params.block_ref,
            issues=[],
        )