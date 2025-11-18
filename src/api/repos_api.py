from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from graph.graph_models import Repo, RepoGraph, RepoStatus, TreeNode
from graph.ingestion import ingest_repo
from supabase_client import supabase
import logging
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
logger.addHandler(handler)

router = APIRouter()

from config import settings

DEMO_ORG_ID = settings.demo_org_id


# ---------------------------------------------------------------------------
# Debug endpoint: basic Supabase connectivity check
# ---------------------------------------------------------------------------

@router.get("/debug/supabase")
async def debug_supabase():
    try:
        res = supabase.table("repos").select("id").limit(1).execute()
        return {"status": "ok", "data": res.data}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class OnboardRepoRequest(BaseModel):
    owner: str
    name: str
    github_url: str
    default_branch: Optional[str] = "main"


class RepoResponse(BaseModel):
    id: str
    owner: str
    name: str
    github_url: str
    default_branch: str
    status: RepoStatus
    last_error: Optional[str] = None


def _row_to_repo(row: dict) -> Repo:
    return Repo(
        id=str(row["id"]),
        owner=row["owner"],
        name=row["name"],
        github_url=row["github_url"],
        default_branch=row.get("default_branch") or "main",
        status=RepoStatus(row.get("status", RepoStatus.pending.value)),
        last_error=row.get("last_error"),
        created_at=row.get("created_at") or datetime.now(timezone.utc),
        updated_at=row.get("updated_at") or datetime.now(timezone.utc),
    )


def _row_to_repo_response(row: dict) -> RepoResponse:
    repo = _row_to_repo(row)
    return RepoResponse(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        github_url=repo.github_url,
        default_branch=repo.default_branch,
        status=repo.status,
        last_error=repo.last_error,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/repos", response_model=RepoResponse)
async def onboard_repo(body: OnboardRepoRequest) -> RepoResponse:
    """
    Onboard a new repository by cloning it and building its graph.

    Phase 0:
      - All repos are associated with a single demo org (DEMO_ORG_ID).
      - Ingestion is synchronous and blocking.
      - Tree and graph are stored in Supabase as JSON blobs.
    """
    owner = body.owner.strip()
    name = body.name.strip()
    github_url = body.github_url.strip()
    default_branch = body.default_branch or "main"

    logger.info(f"Onboarding repo: owner={owner}, name={name}, url={github_url}")

    # 1) Check if repo already exists for this org + owner + name
    logger.info("Checking if repo already exists in Supabase...")
    existing = supabase.table("repos") \
        .select("*") \
        .eq("org_id", DEMO_ORG_ID) \
        .eq("owner", owner) \
        .eq("name", name) \
        .limit(1) \
        .execute()

    repo_row: Optional[dict] = None
    if existing.data:
        repo_row = existing.data[0]
    else:
        # 2) Insert new repo row with status 'pending' / 'cloning'
        insert_res = supabase.table("repos").insert({
            "owner": owner,
            "name": name,
            "github_url": github_url,
            "default_branch": default_branch,
            "status": "cloning",
            "org_id": DEMO_ORG_ID,
        }).execute()

        if not insert_res.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create repo record in Supabase.",
            )
        repo_row = insert_res.data[0]
        logger.info(f"Inserted new repo row with id={repo_row['id']}")

    # Build a Repo model from the row so ingest_repo can use it
    repo = _row_to_repo(repo_row)

    try:
        logger.info(f"Starting ingestion for repo id={repo.id}")
        # 3) Run ingestion pipeline (clone + parse + graph)
        tree, graph = ingest_repo(repo)

        logger.info(f"Ingestion complete for repo id={repo.id}")

        # 4) Store tree and graph JSON in Supabase.
        #    Simple approach: delete any existing rows for this repo_id, then insert.
        logger.info("Storing tree and graph JSON in Supabase...")
        supabase.table("repo_trees").delete().eq("repo_id", repo.id).execute()
        supabase.table("repo_trees").insert({
            "repo_id": repo.id,
            "tree_json": tree.model_dump(mode="json"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        supabase.table("repo_graphs").delete().eq("repo_id", repo.id).execute()
        supabase.table("repo_graphs").insert({
            "repo_id": repo.id,
            "graph_json": graph.model_dump(mode="json"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        # 5) Update repo status to 'ready'
        update_res = supabase.table("repos").update({
            "status": "ready",
            "last_error": None,
            "last_ingested_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", repo.id).execute()

        if update_res.data:
            repo_row = update_res.data[0]
        else:
            # If update didn't return data, keep old row but status is logically 'ready'
            repo_row["status"] = "ready"
            repo_row["last_error"] = None

        logger.info(f"Repo {repo.id} marked as ready.")

    except Exception as e:
        # On any error, mark repo as 'error' and store the message
        error_message = str(e)
        logger.error(f"Ingestion failed for repo {repo.id}: {error_message}")
        supabase.table("repos").update({
            "status": "error",
            "last_error": error_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", repo.id).execute()

        repo_row["status"] = "error"
        repo_row["last_error"] = error_message

    return _row_to_repo_response(repo_row)


@router.get("/repos", response_model=List[RepoResponse])
async def list_repos() -> List[RepoResponse]:
    """
    List all repos for the demo org.

    Phase 0: we don't have real auth, so everything is scoped to DEMO_ORG_ID.
    """
    res = supabase.table("repos") \
        .select("*") \
        .eq("org_id", DEMO_ORG_ID) \
        .order("created_at", desc=True) \
        .execute()

    rows = res.data or []
    logger.info(f"Listing {len(rows)} repos for org={DEMO_ORG_ID}")
    return [_row_to_repo_response(row) for row in rows]


@router.get("/repos/{repo_id}", response_model=RepoResponse)
async def get_repo(repo_id: str) -> RepoResponse:
    """
    Fetch a single repo by its id.
    """
    res = supabase.table("repos") \
        .select("*") \
        .eq("id", repo_id) \
        .eq("org_id", DEMO_ORG_ID) \
        .limit(1) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Repo not found")

    logger.info(f"Fetched repo {repo_id}")
    return _row_to_repo_response(res.data[0])


@router.get("/repos/{repo_id}/tree", response_model=TreeNode)
async def get_repo_tree(repo_id: str) -> TreeNode:
    """
    Fetch the most recent tree snapshot for a repo.
    """
    # Ensure repo belongs to our demo org
    repo_res = supabase.table("repos") \
        .select("id") \
        .eq("id", repo_id) \
        .eq("org_id", DEMO_ORG_ID) \
        .limit(1) \
        .execute()

    if not repo_res.data:
        raise HTTPException(status_code=404, detail="Repo not found")

    res = supabase.table("repo_trees") \
        .select("tree_json") \
        .eq("repo_id", repo_id) \
        .order("generated_at", desc=True) \
        .limit(1) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Tree not found for repo")

    tree_json = res.data[0]["tree_json"]
    logger.info(f"Fetched tree for repo {repo_id}")
    return TreeNode.model_validate(tree_json)


@router.get("/repos/{repo_id}/graph", response_model=RepoGraph)
async def get_repo_graph(repo_id: str) -> RepoGraph:
    """
    Fetch the most recent graph snapshot for a repo.
    """
    # Ensure repo belongs to our demo org
    repo_res = supabase.table("repos") \
        .select("id") \
        .eq("id", repo_id) \
        .eq("org_id", DEMO_ORG_ID) \
        .limit(1) \
        .execute()

    if not repo_res.data:
        raise HTTPException(status_code=404, detail="Repo not found")

    res = supabase.table("repo_graphs") \
        .select("graph_json") \
        .eq("repo_id", repo_id) \
        .order("generated_at", desc=True) \
        .limit(1) \
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Graph not found for repo")

    graph_json = res.data[0]["graph_json"]
    logger.info(f"Fetched graph for repo {repo_id}")
    return RepoGraph.model_validate(graph_json)