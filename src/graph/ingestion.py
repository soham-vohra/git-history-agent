from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from config import settings
from graph.graph_models import (
    Repo,
    RepoGraph,
    TreeNode,
    BlockNode,
    BlockKind,
    GraphEdge,
    EdgeType,
)


IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


def get_repo_path(repo: Repo) -> Path:
    """
    Compute the local filesystem path where this repo will live.
    """
    return settings.repo_base_dir / repo.id


def clone_repo(repo: Repo) -> Path:
    """
    Ensure the repo is cloned locally and return its root path.

    For now this is a simple blocking clone:
      - If the directory already exists, we assume it is usable.
      - Otherwise we perform `git clone <github_url> <target_dir>`.
    """
    target = get_repo_path(repo)
    if target.exists() and any(target.iterdir()):
        return target

    target.parent.mkdir(parents=True, exist_ok=True)

    # Basic blocking clone. Later we can add auth, shallow clones, etc.
    completed = subprocess.run(
        ["git", "clone", repo.github_url, str(target)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git clone failed for {repo.github_url}: {completed.stderr.strip()}"
        )

    return target


def _detect_language(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix in {".js", ".jsx"}:
        return "javascript"
    if suffix in {".java"}:
        return "java"
    if suffix in {".go"}:
        return "go"
    if suffix in {".cs"}:
        return "csharp"
    return None


def build_tree(repo: Repo, root: Path) -> TreeNode:
    """
    Build a TreeNode representation of the repo filesystem.
    """
    root_id = ""
    root_node = TreeNode(
        id=root_id,
        name=repo.name,
        path="",
        type="dir",
        children=[],
    )

    nodes: Dict[str, TreeNode] = {root_id: root_node}

    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out ignored directories in-place so os.walk does not descend into them.
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

        dirpath_path = Path(dirpath)
        rel_dir = os.path.relpath(dirpath_path, root)
        if rel_dir == ".":
            rel_dir = ""

        parent_key = "" if rel_dir == "" else os.path.dirname(rel_dir)
        parent_key = "" if parent_key == "." else parent_key

        # Ensure directory node exists (skip root which we already created)
        if rel_dir != "" and rel_dir not in nodes:
            dir_node = TreeNode(
                id=rel_dir,
                name=os.path.basename(rel_dir),
                path=rel_dir,
                type="dir",
                children=[],
            )
            nodes[rel_dir] = dir_node
            parent = nodes.get(parent_key, root_node)
            parent.children.append(dir_node)

        # Files
        for filename in filenames:
            file_path = dirpath_path / filename
            rel_file = os.path.relpath(file_path, root)
            rel_file = rel_file.replace("\\", "/")
            dir_key = rel_dir

            file_node = TreeNode(
                id=rel_file,
                name=filename,
                path=rel_file,
                type="file",
                language=_detect_language(file_path),
                children=[],
                block_ids=[],
            )

            nodes[rel_file] = file_node
            parent = nodes.get(dir_key, root_node)
            parent.children.append(file_node)

    return root_node


def _iter_python_files(root: Path) -> List[Path]:
    py_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        for filename in filenames:
            if filename.endswith(".py"):
                py_files.append(Path(dirpath) / filename)
    return py_files


def _decorator_name(dec: ast.expr) -> str:
    # Turn a decorator expression into a dotted name string, e.g. app.get, router.post
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        parts: List[str] = []
        cur: ast.AST | None = dec
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return ""


FASTAPI_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options"}


def _infer_block_kind(fn: ast.AST) -> BlockKind:
    for dec in getattr(fn, "decorator_list", []):
        name = _decorator_name(dec)
        # crude heuristic: app.get, app.post, router.get, etc.
        parts = name.split(".")
        if len(parts) >= 2 and parts[-1].lower() in FASTAPI_HTTP_METHODS:
            return BlockKind.endpoint
    return BlockKind.function


def extract_blocks(repo: Repo, root: Path) -> List[BlockNode]:
    """
    Extract BlockNode objects from source files in the repo.

    V1: Python only. We detect:
      - top-level functions (sync + async) as BlockKind.function
      - class methods (sync + async) as BlockKind.function, with `ClassName.method` names
      - FastAPI-style endpoints via decorators as BlockKind.endpoint
    """

    def add_block(
        fn: ast.AST,
        rel_path: str,
        class_name: str | None = None,
    ) -> None:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return

        kind = _infer_block_kind(fn)
        start_line = getattr(fn, "lineno", 1)
        end_line = getattr(fn, "end_lineno", start_line)
        docstring = ast.get_docstring(fn)

        if class_name:
            simple_name = f"{class_name}.{fn.name}"
        else:
            simple_name = fn.name  # type: ignore[attr-defined]

        block_id = f"{rel_path}:{simple_name}"

        block = BlockNode(
            id=block_id,
            repo_id=repo.id,
            name=simple_name,
            kind=kind,
            file_path=rel_path,
            language="python",
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
        )
        block.compute_loc()
        blocks.append(block)

    blocks: List[BlockNode] = []

    for file_path in _iter_python_files(root):
        rel_path = os.path.relpath(file_path, root).replace("\\", "/")
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        # Top-level functions (sync + async)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                add_block(node, rel_path)
            elif isinstance(node, ast.ClassDef):
                # Methods inside classes
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        add_block(item, rel_path, class_name=node.name)

    return blocks


def build_graph(repo: Repo, blocks: List[BlockNode]) -> RepoGraph:
    """
    Build a minimal RepoGraph from extracted blocks.

    For now we only populate nodes and leave edges empty.
    We can add call/import/owns edges later.
    """
    edges: List[GraphEdge] = []
    return RepoGraph(
        repo_id=repo.id,
        nodes=blocks,
        edges=edges,
    )


def ingest_repo(repo: Repo) -> Tuple[TreeNode, RepoGraph]:
    """
    End-to-end ingestion pipeline for a single repo.
    """
    root = clone_repo(repo)
    tree = build_tree(repo, root)
    blocks = extract_blocks(repo, root)
    graph = build_graph(repo, blocks)
    return tree, graph
