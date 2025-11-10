from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from models import BlockRef
from agent import GitHistoryAgent
from git_core import GitError


app = FastAPI()

agent = GitHistoryAgent()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173"] if using Vite/React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    block_ref: BlockRef
    question: str


class ChatResponse(BaseModel):
    answer: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
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
