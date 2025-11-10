from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from models import BlockRef
from agent import GitHistoryAgent
from git_core import GitError


app = FastAPI()

agent = GitHistoryAgent()


class ChatRequest(BaseModel):
    """Request model for the /chat endpoint.

    Attributes:
        block_ref: BlockRef specifying the code block to analyze.
        question: The question to ask about the code block.
    """
    block_ref: BlockRef
    question: str


class ChatResponse(BaseModel):
    """Response model for the /chat endpoint.

    Attributes:
        answer: The LLM's answer to the question about the code block.
    """
    answer: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """FastAPI endpoint handler for chat requests about code blocks.

    Accepts a code block reference and a question, then uses the GitHistoryAgent
    to generate an answer based on code context and git history.

    Args:
        req: ChatRequest containing the block reference and question.

    Returns:
        ChatResponse: Response containing the LLM's answer.

    Raises:
        HTTPException: 400 if a GitError occurs, 500 for other server errors.
    """
    try:
        answer = agent.answer_question(
            block_ref=req.block_ref,
            question=req.question,
        )
    except GitError as e:
        raise HTTPException(status_code=400, detail=f"Git error: {e}")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

    return ChatResponse(answer=answer)