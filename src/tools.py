from __future__ import annotations

from pydantic import BaseModel, Field

from models import BlockRef, CodeContext, HistoryContext
from git_core import get_code_context, build_history_context


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
    a clean interface for LLM tool execution.

    Args:
        params: GetHistoryContextInput containing the block reference and
            maximum commit count.

    Returns:
        HistoryContext: A model containing blame information, commit summaries,
            and PR discussions (PRs currently empty, reserved for future use).
    """
    return build_history_context(
        block_ref=params.block_ref,
        max_commits=params.max_commits,
    )