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
    block_ref: BlockRef
    question: str


class ChatResponse(BaseModel):
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
