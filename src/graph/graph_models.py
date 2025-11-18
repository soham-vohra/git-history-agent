from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


# --- Repo-level metadata -----------------------------------------------------
class RepoStatus(str, Enum):
    pending = "pending"
    cloning = "cloning"
    parsing = "parsing"
    graphing = "graphing"
    ready = "ready"
    error = "error"


class Repo(BaseModel):
    """
    Logical representation of a repository onboarded into Andromeda.
    """

    id: str
    owner: str
    name: str
    github_url: str
    default_branch: str = "main"

    status: RepoStatus = RepoStatus.pending
    last_error: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def display_name(self) -> str:
        return f"{self.owner}/{self.name}"


# --- Tree representation (filesystem view) -----------------------------------
class TreeNode(BaseModel):
    """
    Recursive representation of the repo filesystem tree.
    """

    id: str  # unique within repo (often equal to path)
    name: str
    path: str  # path relative to repo root, e.g. "backend/cine_api.py"
    type: Literal["dir", "file"]

    language: Optional[str] = None  # only really used for files
    children: List["TreeNode"] = Field(default_factory=list)

    # IDs of BlockNode objects that live in this file (for type == "file").
    block_ids: List[str] = Field(default_factory=list)


# --- Code graph representation -----------------------------------------------
class BlockKind(str, Enum):
    function = "function"
    method = "method"
    class_ = "class"
    module = "module"
    endpoint = "endpoint"
    job = "job"
    unknown = "unknown"


class BlockNode(BaseModel):
    """
    Node in the code graph: a function, method, class, endpoint, etc.
    """

    id: str  # e.g. "backend/cine_api.py:get_movies"
    repo_id: str

    name: str  # e.g. "GET /movies" or "add_movie"
    kind: BlockKind = BlockKind.unknown

    file_path: str  # e.g. "backend/cine_api.py"
    language: Optional[str] = None

    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    loc: Optional[int] = None  # can be computed as end_line - start_line + 1

    # Optional descriptive metadata
    docstring: Optional[str] = None
    http_method: Optional[str] = None  # "GET", "POST", etc.
    http_path: Optional[str] = None    # "/movies", "/user_rating", etc.

    # Optional change metadata (hook for git-based enrichments later)
    last_modified: Optional[datetime] = None
    last_author: Optional[str] = None
    commit_count: int = 0
    churn_score: Optional[float] = None  # 0–1 heuristic for volatility

    def compute_loc(self) -> int:
        loc = self.end_line - self.start_line + 1
        self.loc = loc
        return loc


class EdgeType(str, Enum):
    call = "call"         # A calls B
    import_ = "import"    # file/module-level import
    inherit = "inherit"   # class extends/implements
    owns = "owns"         # class owns method, module owns function, etc.
    test = "test"         # test block exercising target
    unknown = "unknown"


class GraphEdge(BaseModel):
    """
    Directed relationship between two BlockNode objects.
    """

    id: str  # e.g. "source_id->target_id:type"
    repo_id: str

    source_id: str
    target_id: str
    type: EdgeType = EdgeType.unknown

    weight: float = 1.0  # strength / count of occurrences, etc.


class RepoGraph(BaseModel):
    """
    Snapshot of the full code graph for a repo.
    """

    repo_id: str
    nodes: List[BlockNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Optional place to stash layout info if you pre-compute positions
    layout: Optional[dict] = None


# Pydantic forward-ref resolution for recursive models
TreeNode.model_rebuild()
RepoGraph.model_rebuild()