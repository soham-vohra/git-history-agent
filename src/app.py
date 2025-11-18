from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat_api import router as chat_router
from api.repos_api import router as repos_router

app = FastAPI(title="Andromeda backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(repos_router, prefix="/api")