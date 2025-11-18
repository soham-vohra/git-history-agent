from __future__ import annotations

import os
from typing import Optional, List

import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models import BlockRef, LinearIssue, LinearTeam, PRDiscussionSummary
from agent import GitHistoryAgent
from git_core import GitError
from linear_client import LinearClient, LinearError
from conversation_memory import get_conversation_memory

# Import session endpoints (must be after app is defined)
# This ensures the endpoints are registered with the FastAPI app
try:
    from llm_client_sessions import *  # noqa: F401, F403
except ImportError:
    # If import fails, endpoints won't be available (shouldn't happen in normal usage)
    pass

# Import GitHub client (optional)
try:
    from github_client import GitHubClient, GitHubError as GitHubAPIError
    from github_utils import github_pr_to_pr_summary
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    GitHubClient = None
    GitHubAPIError = None
    github_pr_to_pr_summary = None


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

# Initialize agent with provider from environment variable (default: openai)
# Set LLM_PROVIDER=gemini to use Gemini with context caching
provider = os.getenv("LLM_PROVIDER", "openai").lower()
use_caching = os.getenv("USE_CONTEXT_CACHING", "true").lower() == "true"
cache_ttl = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

agent = GitHistoryAgent(
    provider=provider,
    use_context_caching=use_caching if provider == "gemini" else False,
    cache_ttl_seconds=cache_ttl,
)

# Initialize Linear client (will raise error if API key not set, but that's okay)
try:
    linear_client = LinearClient()
except LinearError:
    linear_client = None

# Initialize GitHub client (optional - works without API key for public repos)
github_client = None
if GITHUB_AVAILABLE and GitHubClient:
    try:
        # GitHub client can work without API key for public repos
        # It will just have lower rate limits (60 vs 5000 requests/hour)
        github_client = GitHubClient()
    except Exception:
        # If initialization fails, continue without GitHub client
        github_client = None


class ChatRequest(BaseModel):
    """Request model for the /chat endpoint.

    Attributes:
        block_ref: BlockRef specifying the code block to analyze.
        question: The question to ask about the code block.
        session_id: Optional session ID for conversation memory. If provided,
            the conversation history will be maintained across requests.
    """
    block_ref: BlockRef
    question: str
    session_id: Optional[str] = None


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
    to generate an answer based on code context and git history. Supports
    conversation memory via session_id for maintaining context across requests.

    Args:
        req: ChatRequest containing the block reference, question, and optional session_id.
        request: FastAPI Request object for accessing headers (e.g., Origin for CORS).

    Returns:
        JSONResponse: Response containing the LLM's answer with explicit CORS headers.

    Raises:
        HTTPException: 400 if a GitError occurs, 500 for other server errors.
    """
    memory = get_conversation_memory()
    conversation_history = None
    
    # Get conversation history if session_id is provided
    if req.session_id:
        history = memory.get_conversation_history(req.session_id, max_messages=10)
        if history:
            conversation_history = history.get("messages", [])
        
        # Add user message to conversation
        memory.add_message(
            session_id=req.session_id,
            role="user",
            content=req.question,
            block_ref=req.block_ref,
        )
    
    try:
        answer = agent.answer_question(
            block_ref=req.block_ref,
            question=req.question,
            conversation_history=conversation_history,
        )
        
        # Add assistant response to conversation if session_id is provided
        if req.session_id:
            memory.add_message(
                session_id=req.session_id,
                role="assistant",
                content=answer,
                block_ref=req.block_ref,
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


# ============================================================================
# Linear API Endpoints
# ============================================================================

class SearchIssuesRequest(BaseModel):
    """Request model for searching Linear issues."""
    query: Optional[str] = None
    team_id: Optional[str] = None
    state: Optional[str] = None
    limit: int = 20


class CreateIssueRequest(BaseModel):
    """Request model for creating a Linear issue."""
    team_id: str
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    state_id: Optional[str] = None
    priority: Optional[int] = None
    label_ids: Optional[List[str]] = None


class CommentRequest(BaseModel):
    """Request model for adding a comment to a Linear issue."""
    body: str


@app.get("/linear/teams")
async def get_linear_teams(request: Request) -> JSONResponse:
    """Get all Linear teams.

    Returns:
        JSONResponse: List of teams with CORS headers.
    """
    if not linear_client:
        raise HTTPException(status_code=503, detail="Linear API not configured")

    try:
        teams_dict = linear_client.get_teams()
        teams = [LinearTeam(**team) for team in teams_dict]
        payload = {"teams": [team.model_dump() for team in teams]}
        resp = JSONResponse(content=payload)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except LinearError as e:
        raise HTTPException(status_code=400, detail=f"Linear error: {e}")


@app.get("/linear/issues/{issue_id}")
async def get_linear_issue(issue_id: str, request: Request) -> JSONResponse:
    """Get a specific Linear issue by ID.

    Args:
        issue_id: Linear issue ID.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: Issue information with CORS headers.
    """
    if not linear_client:
        raise HTTPException(status_code=503, detail="Linear API not configured")

    try:
        from tools import _dict_to_linear_issue
        
        issue_dict = linear_client.get_issue(issue_id)
        if not issue_dict:
            raise HTTPException(status_code=404, detail="Issue not found")
        
        issue = _dict_to_linear_issue(issue_dict)
        payload = issue.model_dump()
        resp = JSONResponse(content=payload)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except LinearError as e:
        raise HTTPException(status_code=400, detail=f"Linear error: {e}")


@app.post("/linear/issues/search")
async def search_linear_issues(req: SearchIssuesRequest, request: Request) -> JSONResponse:
    """Search for Linear issues.

    Args:
        req: SearchIssuesRequest containing search parameters.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: List of matching issues with CORS headers.
    """
    if not linear_client:
        raise HTTPException(status_code=503, detail="Linear API not configured")

    try:
        from tools import search_linear_issues_tool, SearchLinearIssuesInput
        
        result = search_linear_issues_tool(
            SearchLinearIssuesInput(
                query=req.query,
                team_id=req.team_id,
                state=req.state,
                limit=req.limit,
            )
        )
        payload = {"issues": [issue.model_dump() for issue in result]}
        resp = JSONResponse(content=payload)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except LinearError as e:
        raise HTTPException(status_code=400, detail=f"Linear error: {e}")


@app.post("/linear/issues")
async def create_linear_issue(req: CreateIssueRequest, request: Request) -> JSONResponse:
    """Create a new Linear issue.

    Args:
        req: CreateIssueRequest containing issue details.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: Created issue information with CORS headers.
    """
    if not linear_client:
        raise HTTPException(status_code=503, detail="Linear API not configured")

    try:
        from tools import create_linear_issue_tool, CreateLinearIssueInput
        
        result = create_linear_issue_tool(
            CreateLinearIssueInput(
                team_id=req.team_id,
                title=req.title,
                description=req.description,
                assignee_id=req.assignee_id,
                state_id=req.state_id,
                priority=req.priority,
                label_ids=req.label_ids,
            )
        )
        payload = result.model_dump()
        resp = JSONResponse(content=payload)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except LinearError as e:
        raise HTTPException(status_code=400, detail=f"Linear error: {e}")


@app.post("/linear/issues/{issue_id}/comments")
async def add_linear_comment(issue_id: str, req: CommentRequest, request: Request) -> JSONResponse:
    """Add a comment to a Linear issue.

    Args:
        issue_id: Linear issue ID.
        req: CommentRequest containing comment body.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: Created comment information with CORS headers.
    """
    if not linear_client:
        raise HTTPException(status_code=503, detail="Linear API not configured")

    try:
        comment_dict = linear_client.add_comment_to_issue(issue_id, req.body)
        payload = comment_dict
        resp = JSONResponse(content=payload)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except LinearError as e:
        raise HTTPException(status_code=400, detail=f"Linear error: {e}")


# ============================================================================
# GitHub API Endpoints
# ============================================================================

class GetPRsForCommitsRequest(BaseModel):
    """Request model for getting PRs for commits."""
    commit_shas: List[str]


class SearchPRsRequest(BaseModel):
    """Request model for searching GitHub PRs."""
    query: Optional[str] = None
    state: str = "all"
    limit: int = 10


@app.get("/github/repos/{owner}/{repo}/pulls/{pr_number}")
async def get_github_pr(
    owner: str,
    repo: str,
    pr_number: int,
    request: Request,
) -> JSONResponse:
    """Get a specific GitHub pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pr_number: Pull request number.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: PR information with CORS headers.
    """
    if not github_client:
        raise HTTPException(status_code=503, detail="GitHub API not available")

    try:
        pr_data = github_client.get_pull_request(owner, repo, pr_number)
        resp = JSONResponse(content=pr_data)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except GitHubAPIError as e:
        raise HTTPException(status_code=400, detail=f"GitHub error: {e}")


@app.post("/github/repos/{owner}/{repo}/pulls/search")
async def search_github_prs(
    owner: str,
    repo: str,
    req: SearchPRsRequest,
    request: Request,
) -> JSONResponse:
    """Search for GitHub pull requests.

    Args:
        owner: Repository owner.
        repo: Repository name.
        req: SearchPRsRequest containing search parameters.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: List of matching PRs with CORS headers.
    """
    if not github_client:
        raise HTTPException(status_code=503, detail="GitHub API not available")

    try:
        prs = github_client.search_prs(
            owner=owner,
            repo=repo,
            query=req.query,
            state=req.state,
            limit=req.limit,
        )
        payload = {"prs": prs}
        resp = JSONResponse(content=payload)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except GitHubAPIError as e:
        raise HTTPException(status_code=400, detail=f"GitHub error: {e}")


@app.post("/github/repos/{owner}/{repo}/commits/prs")
async def get_prs_for_commits(
    owner: str,
    repo: str,
    req: GetPRsForCommitsRequest,
    request: Request,
) -> JSONResponse:
    """Get PRs associated with commit SHAs.

    Args:
        owner: Repository owner.
        repo: Repository name.
        req: GetPRsForCommitsRequest containing commit SHAs.
        request: FastAPI Request object for CORS headers.

    Returns:
        JSONResponse: Dictionary mapping commit SHA to list of PRs.
    """
    if not github_client:
        raise HTTPException(status_code=503, detail="GitHub API not available")

    try:
        commit_to_prs = github_client.get_prs_for_commits(
            owner=owner,
            repo=repo,
            commit_shas=req.commit_shas,
        )
        resp = JSONResponse(content=commit_to_prs)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except GitHubAPIError as e:
        raise HTTPException(status_code=400, detail=f"GitHub error: {e}")


@app.get("/github/repos/{owner}/{repo}/pulls/{pr_number}/discussion")
async def get_github_pr_discussion(
    owner: str,
    repo: str,
    pr_number: int,
    request: Request,
    include_reviews: bool = True,
    include_comments: bool = True,
) -> JSONResponse:
    """Get complete PR discussion including reviews and comments.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pr_number: Pull request number.
        request: FastAPI Request object for CORS headers.
        include_reviews: Whether to include review comments.
        include_comments: Whether to include issue comments.

    Returns:
        JSONResponse: PR discussion data with CORS headers.
    """
    if not github_client:
        raise HTTPException(status_code=503, detail="GitHub API not available")

    try:
        discussion = github_client.get_pr_discussion(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            include_reviews=include_reviews,
            include_comments=include_comments,
            max_comments=50,
        )
        resp = JSONResponse(content=discussion)
        resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
            "Origin", "http://localhost:5173"
        )
        return resp
    except GitHubAPIError as e:
        raise HTTPException(status_code=400, detail=f"GitHub error: {e}")

# ============================================================================
# Conversation Memory Endpoints
# ============================================================================

class CreateSessionRequest(BaseModel):
    """Request model for creating a conversation session."""
    block_ref: Optional[BlockRef] = None


class SessionResponse(BaseModel):
    """Response model for session operations."""
    session_id: str
    created_at: float
    message_count: int = 0


@app.post("/chat/sessions", response_model=SessionResponse)
async def create_session(
    req: CreateSessionRequest,
    request: Request,
) -> JSONResponse:
    """Create a new conversation session."""
    memory = get_conversation_memory()
    session_id = memory.create_session(initial_block_ref=req.block_ref)
    session = memory.get_session(session_id)
    
    payload = {
        "session_id": session_id,
        "created_at": session.created_at if session else time.time(),
        "message_count": len(session.messages) if session else 0,
    }
    
    resp = JSONResponse(content=payload)
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
        "Origin", "http://localhost:5173"
    )
    return resp


@app.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    max_messages: int = 10,
) -> JSONResponse:
    """Get conversation history for a session."""
    memory = get_conversation_memory()
    history = memory.get_conversation_history(session_id, max_messages=max_messages)
    
    if not history:
        raise HTTPException(status_code=404, detail="Session not found")
    
    resp = JSONResponse(content=history)
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
        "Origin", "http://localhost:5173"
    )
    return resp


@app.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
) -> JSONResponse:
    """Delete a conversation session."""
    memory = get_conversation_memory()
    deleted = memory.delete_session(session_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    
    resp = JSONResponse(content={"success": True, "session_id": session_id})
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
        "Origin", "http://localhost:5173"
    )
    return resp


@app.get("/chat/sessions")
async def list_sessions(
    request: Request,
) -> JSONResponse:
    """Get statistics about active sessions."""
    memory = get_conversation_memory()
    stats = memory.get_session_stats()
    
    resp = JSONResponse(content=stats)
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get(
        "Origin", "http://localhost:5173"
    )
    return resp
