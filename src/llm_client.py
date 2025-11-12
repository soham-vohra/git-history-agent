from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models import BlockRef
from agent import GitHistoryAgent
from git_core import GitError


app = FastAPI()

# 🔧 CORS: explicitly allow your Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,  # keep simple for dev; add cookies later if needed
    allow_methods=["*"],      # includes OPTIONS, POST, etc.
    allow_headers=["*"],
)

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


# ✅ Explicit preflight handler for /chat (OPTIONS)
@app.options("/chat")
async def chat_options(request: Request) -> JSONResponse:
    """
    Handles CORS preflight for the /chat endpoint.
    This makes sure the browser gets the Access-Control-* headers it needs.
    """
    resp = JSONResponse({"ok": True})
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
        "Origin", "http://localhost:5173"
    )
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> JSONResponse:
    """FastAPI endpoint handler for chat requests about code blocks.

    Accepts a code block reference and a question, then uses the GitHistoryAgent
    to generate an answer based on code context and git history.

    Args:
        req: ChatRequest containing the block reference and question.
        request: FastAPI Request object for accessing headers (e.g., Origin for CORS).

    Returns:
        JSONResponse: Response containing the LLM's answer with explicit CORS headers.

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

    # Wrap in JSONResponse so we can be explicit about CORS headers as well
    payload = ChatResponse(answer=answer).model_dump()
    resp = JSONResponse(content=payload)
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
        "Origin", "http://localhost:5173"
    )
    return resp
