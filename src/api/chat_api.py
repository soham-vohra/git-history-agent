from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.models import BlockRef
from core.agent import GitHistoryAgent
from core.git_core import GitError

# Router for all chat-related endpoints
router = APIRouter()

# Single shared agent instance for handling questions
agent = GitHistoryAgent()


class ChatRequest(BaseModel):
    block_ref: BlockRef
    question: str


class ChatResponse(BaseModel):
    answer: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.

    The frontend sends:
      - block_ref: identifies the code block in the repo
      - question: the user's natural language question

    We forward this to the GitHistoryAgent, which may call tools
    (code context, history context, etc.) and return a final answer.
    """
    try:
        answer = agent.answer_question(
            block_ref=req.block_ref,
            question=req.question,
        )
    except GitError as e:
        # Git-specific problems (bad ref, repo issues, etc.)
        raise HTTPException(status_code=400, detail=f"Git error: {e}")
    except Exception:
        # Catch-all for unexpected failures
        raise HTTPException(status_code=500, detail="Internal server error")

    return ChatResponse(answer=answer)