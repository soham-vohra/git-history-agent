from __future__ import annotations

from pydantic import BaseModel, Field

from models import BlockRef, CodeContext, HistoryContext
from git_core import get_code_context, build_history_context


class GetCodeContextInput(BaseModel):
    block_ref: BlockRef
    context_lines: int = Field(10, ge=0) # +/- how many lines we want to pull in for context


class GetHistoryContextInput(BaseModel):
    block_ref: BlockRef
    max_commits: int = Field(10, ge=1)


def get_code_context_tool(params: GetCodeContextInput) -> CodeContext:
    return get_code_context(
        block_ref=params.block_ref,
        context_lines=params.context_lines,
    )


def get_history_context_tool(params: GetHistoryContextInput) -> HistoryContext:
    return build_history_context(
        block_ref=params.block_ref,
        max_commits=params.max_commits,
    )