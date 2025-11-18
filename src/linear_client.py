from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# Linear API endpoint
LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearError(RuntimeError):
    """Exception raised for Linear API errors."""
    pass


class LinearClient:
    """Client for interacting with Linear's GraphQL API."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Linear client.

        Args:
            api_key: Linear API key. If not provided, will try to get from
                LINEAR_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("LINEAR_API_KEY")
        if not self.api_key:
            raise LinearError(
                "Linear API key not found. Set LINEAR_API_KEY environment variable."
            )
        # Linear API requires Bearer token format
        auth_header = self.api_key if self.api_key.startswith("Bearer ") else f"Bearer {self.api_key}"
        self.headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against Linear's API.

        Args:
            query: GraphQL query string.
            variables: Optional variables for the query.

        Returns:
            Dict[str, Any]: Response data from the API.

        Raises:
            LinearError: If the API request fails or returns errors.
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    LINEAR_API_URL,
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    error_messages = [e.get("message", "Unknown error") for e in data["errors"]]
                    raise LinearError(f"Linear API errors: {', '.join(error_messages)}")

                return data.get("data", {})
        except httpx.HTTPError as e:
            raise LinearError(f"HTTP error while calling Linear API: {e}")
        except Exception as e:
            raise LinearError(f"Unexpected error calling Linear API: {e}")

    def get_teams(self) -> List[Dict[str, Any]]:
        """Get all teams from Linear workspace.

        Returns:
            List[Dict[str, Any]]: List of team information dictionaries.
        """
        query = """
        query {
            teams {
                nodes {
                    id
                    key
                    name
                }
            }
        }
        """
        data = self._execute_query(query)
        return data.get("teams", {}).get("nodes", [])

    def get_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific issue by ID.

        Args:
            issue_id: Linear issue ID.

        Returns:
            Dict[str, Any]: Issue information, or None if not found.
        """
        query = """
        query GetIssue($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                state {
                    name
                    type
                }
                assignee {
                    name
                    email
                }
                creator {
                    name
                    email
                }
                createdAt
                updatedAt
                url
                priority
                labels {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
        """
        data = self._execute_query(query, {"id": issue_id})
        return data.get("issue")

    def search_issues(
        self,
        query: Optional[str] = None,
        team_id: Optional[str] = None,
        state: Optional[str] = None,
        assignee_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Search for issues in Linear.

        Args:
            query: Search query string (searches title and description).
            team_id: Filter by team ID.
            state: Filter by state name.
            assignee_id: Filter by assignee ID.
            limit: Maximum number of issues to return.

        Returns:
            List[Dict[str, Any]]: List of matching issues.
        """
        # Build filter string
        filters = []
        if team_id:
            filters.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')
        if state:
            filters.append(f'state: {{ name: {{ eq: "{state}" }} }}')
        if assignee_id:
            filters.append(f'assignee: {{ id: {{ eq: "{assignee_id}" }} }}')
        if query:
            filters.append(f'title: {{ containsIgnoreCase: "{query}" }}')

        filter_string = ", ".join(filters) if filters else ""

        graphql_query = f"""
        query {{
            issues(
                filter: {{ {filter_string} }},
                first: {limit}
            ) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    state {{
                        name
                        type
                    }}
                    assignee {{
                        name
                        email
                    }}
                    creator {{
                        name
                        email
                    }}
                    createdAt
                    updatedAt
                    url
                    priority
                    labels {{
                        nodes {{
                            id
                            name
                        }}
                    }}
                }}
            }}
        }}
        """
        data = self._execute_query(graphql_query)
        return data.get("issues", {}).get("nodes", [])

    def create_issue(
        self,
        team_id: str,
        title: str,
        description: Optional[str] = None,
        assignee_id: Optional[str] = None,
        state_id: Optional[str] = None,
        priority: Optional[int] = None,
        label_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a new issue in Linear.

        Args:
            team_id: ID of the team to create the issue in.
            title: Issue title.
            description: Issue description.
            assignee_id: Optional assignee ID.
            state_id: Optional state ID (defaults to team's default state).
            priority: Optional priority (0-4, where 0 is urgent, 4 is none).
            label_ids: Optional list of label IDs.

        Returns:
            Dict[str, Any]: Created issue information.
        """
        mutation = """
        mutation CreateIssue(
            $teamId: String!,
            $title: String!,
            $description: String,
            $assigneeId: String,
            $stateId: String,
            $priority: Int,
            $labelIds: [String!]
        ) {
            issueCreate(
                input: {
                    teamId: $teamId
                    title: $title
                    description: $description
                    assigneeId: $assigneeId
                    stateId: $stateId
                    priority: $priority
                    labelIds: $labelIds
                }
            ) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    state {
                        name
                        type
                    }
                    assignee {
                        name
                        email
                    }
                    creator {
                        name
                        email
                    }
                    createdAt
                    url
                    priority
                }
            }
        }
        """
        variables = {
            "teamId": team_id,
            "title": title,
            "description": description,
            "assigneeId": assignee_id,
            "stateId": state_id,
            "priority": priority,
            "labelIds": label_ids,
        }
        # Remove None values
        variables = {k: v for k, v in variables.items() if v is not None}

        data = self._execute_query(mutation, variables)
        issue_create = data.get("issueCreate", {})
        if not issue_create.get("success"):
            raise LinearError("Failed to create issue in Linear")

        return issue_create.get("issue", {})

    def update_issue(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        state_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update an existing issue.

        Args:
            issue_id: ID of the issue to update.
            title: New title (optional).
            description: New description (optional).
            state_id: New state ID (optional).
            assignee_id: New assignee ID (optional).
            priority: New priority (optional).

        Returns:
            Dict[str, Any]: Updated issue information.
        """
        mutation = """
        mutation UpdateIssue(
            $id: String!,
            $title: String,
            $description: String,
            $stateId: String,
            $assigneeId: String,
            $priority: Int
        ) {
            issueUpdate(
                id: $id
                input: {
                    title: $title
                    description: $description
                    stateId: $stateId
                    assigneeId: $assigneeId
                    priority: $priority
                }
            ) {
                success
                issue {
                    id
                    identifier
                    title
                    description
                    state {
                        name
                        type
                    }
                    assignee {
                        name
                        email
                    }
                    updatedAt
                    url
                    priority
                }
            }
        }
        """
        variables = {
            "id": issue_id,
            "title": title,
            "description": description,
            "stateId": state_id,
            "assigneeId": assignee_id,
            "priority": priority,
        }
        # Remove None values
        variables = {k: v for k, v in variables.items() if v is not None}

        data = self._execute_query(mutation, variables)
        issue_update = data.get("issueUpdate", {})
        if not issue_update.get("success"):
            raise LinearError("Failed to update issue in Linear")

        return issue_update.get("issue", {})

    def add_comment_to_issue(self, issue_id: str, body: str) -> Dict[str, Any]:
        """Add a comment to an issue.

        Args:
            issue_id: ID of the issue to comment on.
            body: Comment body text.

        Returns:
            Dict[str, Any]: Created comment information.
        """
        mutation = """
        mutation CreateComment($issueId: String!, $body: String!) {
            commentCreate(
                input: {
                    issueId: $issueId
                    body: $body
                }
            ) {
                success
                comment {
                    id
                    body
                    createdAt
                    user {
                        name
                        email
                    }
                }
            }
        }
        """
        data = self._execute_query(mutation, {"issueId": issue_id, "body": body})
        comment_create = data.get("commentCreate", {})
        if not comment_create.get("success"):
            raise LinearError("Failed to create comment in Linear")

        return comment_create.get("comment", {})


__all__ = ["LinearClient", "LinearError", "LINEAR_API_URL"]

