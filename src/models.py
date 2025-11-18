from __future__ import annotations

from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class BlockRef(BaseModel):
    repo_owner: str
    repo_name: str
    ref: str
    path: str
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the BlockRef model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the BlockRef model.
        """
        return self.model_dump()


class CodeContext(BaseModel):
    block_ref: BlockRef

    code_block: str
    surrounding_code: str
    context_start_line: int = Field(..., ge=1)
    context_end_line: int = Field(..., ge=1)

    file_total_lines: int = Field(..., ge=0)
    language: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the CodeContext model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the CodeContext model.
        """
        return self.model_dump()


class BlameEntry(BaseModel):
    block_ref: BlockRef

    line: int = Field(..., ge=1)
    code: str

    commit: str
    author: Optional[str] = None
    author_email: Optional[str] = None
    author_time: Optional[str] = None
    summary: Optional[str] = None
    filename: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the BlameEntry model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the BlameEntry model.
        """
        return self.model_dump()


class BlameBlock(BaseModel):
    block_ref: BlockRef

    # All per-line blame information for this block
    entries: List[BlameEntry] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:  # pragma: no cover
        """Convert the BlameBlock model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the BlameBlock model.
        """
        return self.model_dump()


class CommitSummary(BaseModel):
    sha: str
    author: str
    author_email: Optional[str] = None
    date: str
    message: str

    diff_hunks_for_block: List[str] = Field(default_factory=list)
    pr_numbers: Optional[List[int]] = None

    def to_dict(self) -> Dict[str, Any]:  # pragma: no cover
        """Convert the CommitSummary model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the CommitSummary model.
        """
        return self.model_dump()


class PRDiscussionSummary(BaseModel):
    number: int
    title: str
    url: str

    state: str
    merged_at: Optional[str] = None

    summary: str
    key_comments: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:  # pragma: no cover
        """Convert the PRDiscussionSummary model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the PRDiscussionSummary model.
        """
        return self.model_dump()


class HistoryContext(BaseModel):
    block_ref: BlockRef

    blame: Optional[BlameBlock] = None
    commits: List[CommitSummary] = Field(default_factory=list)
    prs: List[PRDiscussionSummary] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:  # pragma: no cover
        """Convert the HistoryContext model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the HistoryContext model.
        """
        return self.model_dump()


class LinearTeam(BaseModel):
    """Model for Linear team information."""

    id: str
    key: str
    name: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert the LinearTeam model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the LinearTeam model.
        """
        return self.model_dump()


class LinearLabel(BaseModel):
    """Model for Linear label information."""

    id: str
    name: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert the LinearLabel model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the LinearLabel model.
        """
        return self.model_dump()


class LinearUser(BaseModel):
    """Model for Linear user information."""

    name: Optional[str] = None
    email: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the LinearUser model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the LinearUser model.
        """
        return self.model_dump()


class LinearIssueState(BaseModel):
    """Model for Linear issue state information."""

    name: str
    type: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert the LinearIssueState model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the LinearIssueState model.
        """
        return self.model_dump()


class LinearIssue(BaseModel):
    """Model for Linear issue information."""

    id: str
    identifier: str
    title: str
    description: Optional[str] = None
    state: Optional[LinearIssueState] = None
    assignee: Optional[LinearUser] = None
    creator: Optional[LinearUser] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    url: Optional[str] = None
    priority: Optional[int] = None
    labels: List[LinearLabel] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the LinearIssue model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the LinearIssue model.
        """
        return self.model_dump()


class LinearIssueContext(BaseModel):
    """Model for Linear issues related to a code block."""

    block_ref: BlockRef
    issues: List[LinearIssue] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the LinearIssueContext model to a dictionary.

        Returns:
            Dict[str, Any]: A dictionary representation of the LinearIssueContext model.
        """
        return self.model_dump()


__all__ = [
    "BlockRef",
    "CodeContext",
    "BlameEntry",
    "BlameBlock",
    "CommitSummary",
    "PRDiscussionSummary",
    "HistoryContext",
    "LinearTeam",
    "LinearLabel",
    "LinearUser",
    "LinearIssueState",
    "LinearIssue",
    "LinearIssueContext",
]