from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Tuple

from models import (
    BlockRef,
    CodeContext,
    BlameEntry,
    BlameBlock,
    CommitSummary,
    HistoryContext,
)


class GitError(RuntimeError):
    pass


def get_repos_root() -> Path:
    env = os.getenv("REPOS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "repos").resolve()


def resolve_repo_path(block_ref: BlockRef) -> Path:
    root = get_repos_root()
    repo_path = root  / block_ref.repo_name
    if not repo_path.exists():
        raise GitError(f"Repo path does not exist: {repo_path}")
    return repo_path


def run_git(args: List[str], repo_path: Path) -> str:
    cmd = ["git", *args]
    result = subprocess.run(
        cmd,
        cwd=str(repo_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"Git command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result.stdout


def read_file_at_ref(block_ref: BlockRef) -> Tuple[List[str], int]:
    repo_path = resolve_repo_path(block_ref)
    spec = f"{block_ref.ref}:{block_ref.path}"
    output = run_git(["show", spec], repo_path)
    lines = output.splitlines()
    return lines, len(lines)


def guess_language_from_path(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix == ".ts":
        return "typescript"
    if suffix == ".js":
        return "javascript"
    if suffix == ".java":
        return "java"
    if suffix in {".cpp", ".cc", ".cxx", ".hpp"}:
        return "cpp"
    if suffix in {".c", ".h"}:
        return "c"
    if suffix == ".go":
        return "go"
    if suffix == ".rs":
        return "rust"
    if suffix == ".rb":
        return "ruby"
    if suffix == ".php":
        return "php"
    return None


def get_code_context(block_ref: BlockRef, context_lines: int = 10) -> CodeContext:
    lines, total = read_file_at_ref(block_ref)

    if block_ref.start_line < 1 or block_ref.end_line > total:
        raise GitError(
            f"Invalid line range {block_ref.start_line}-{block_ref.end_line} for file with {total} lines"
        )
    if block_ref.start_line > block_ref.end_line:
        raise GitError("start_line cannot be greater than end_line")

    start = block_ref.start_line
    end = block_ref.end_line

    ctx_start = max(1, start - context_lines)
    ctx_end = min(total, end + context_lines)

    code_block = "\n".join(lines[start - 1 : end])
    surrounding_code = "\n".join(lines[ctx_start - 1 : ctx_end])

    language = guess_language_from_path(block_ref.path)

    return CodeContext(
        block_ref=block_ref,
        code_block=code_block,
        surrounding_code=surrounding_code,
        context_start_line=ctx_start,
        context_end_line=ctx_end,
        file_total_lines=total,
        language=language,
    )


def parse_blame_porcelain(output: str, block_ref: BlockRef) -> List[BlameEntry]:
    entries: List[BlameEntry] = []
    current: dict | None = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip("\n")

        if line.startswith("\t"):
            if current is not None:
                code = line[1:]
                entry = BlameEntry(
                    block_ref=block_ref,
                    line=current.get("final_lineno"),
                    code=code,
                    commit=current.get("sha"),
                    author=current.get("author"),
                    author_email=current.get("author_mail"),
                    author_time=current.get("author_time"),
                    summary=current.get("summary"),
                    filename=current.get("filename"),
                )
                entries.append(entry)
                current = None
            continue

        if current is None:
            parts = line.split()
            if len(parts) >= 3:
                sha = parts[0]
                final_lineno = int(parts[2])
                current = {"sha": sha, "final_lineno": final_lineno}
            continue

        if " " in line:
            key, value = line.split(" ", 1)
            value = value.strip()
            if key == "author":
                current["author"] = value
            elif key == "author-mail":
                current["author_mail"] = value
            elif key == "author-time":
                current["author_time"] = value
            elif key == "summary":
                current["summary"] = value
            elif key == "filename":
                current["filename"] = value

    return entries


def get_blame_entries(block_ref: BlockRef) -> List[BlameEntry]:
    repo_path = resolve_repo_path(block_ref)
    args = [
        "blame",
        "-L",
        f"{block_ref.start_line},{block_ref.end_line}",
        "--line-porcelain",
        block_ref.ref,
        "--",
        block_ref.path,
    ]
    output = run_git(args, repo_path)
    return parse_blame_porcelain(output, block_ref)


def get_blame_block(block_ref: BlockRef) -> BlameBlock:
    entries = get_blame_entries(block_ref)
    return BlameBlock(block_ref=block_ref, entries=entries)


def get_commit_summaries_for_block(block_ref: BlockRef, max_commits: int = 10) -> Tuple[BlameBlock | None, List[CommitSummary]]:
    blame_block = get_blame_block(block_ref)
    if not blame_block.entries:
        return blame_block, []

    repo_path = resolve_repo_path(block_ref)

    seen = set()
    shas: List[str] = []
    for entry in blame_block.entries:
        sha = entry.commit
        if not sha:
            continue
        if sha not in seen:
            seen.add(sha)
            shas.append(sha)

    shas = shas[:max_commits]

    summaries: List[CommitSummary] = []
    for sha in shas:
        meta_output = run_git([
            "show",
            "-s",
            "--format=%H%n%an%n%ae%n%ad%n%B",
            sha,
        ], repo_path)
        meta_lines = meta_output.splitlines()
        if len(meta_lines) < 4:
            continue

        full_sha = meta_lines[0]
        author = meta_lines[1]
        author_email = meta_lines[2] or None
        date = meta_lines[3]
        message = "\n".join(meta_lines[4:]).strip()

        diff_output = run_git(["show", sha, "--", block_ref.path], repo_path)

        summaries.append(
            CommitSummary(
                sha=full_sha,
                author=author,
                author_email=author_email,
                date=date,
                message=message,
                diff_hunks_for_block=[diff_output],
                pr_numbers=None,
            )
        )

    return blame_block, summaries


def build_history_context(block_ref: BlockRef, max_commits: int = 10) -> HistoryContext:
    try:
        blame_block, commits = get_commit_summaries_for_block(block_ref, max_commits=max_commits)
    except GitError:
        blame_block = None
        commits = []

    return HistoryContext(
        block_ref=block_ref,
        blame=blame_block,
        commits=commits,
        prs=[],
    )


__all__ = [
    "GitError",
    "get_repos_root",
    "resolve_repo_path",
    "run_git",
    "read_file_at_ref",
    "guess_language_from_path",
    "get_code_context",
    "parse_blame_porcelain",
    "get_blame_entries",
    "get_blame_block",
    "get_commit_summaries_for_block",
    "build_history_context",
]
