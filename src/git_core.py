from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from models import (
    BlockRef,
    CodeContext,
    BlameEntry,
    BlameBlock,
    CommitSummary,
    HistoryContext,
    PRDiscussionSummary,
)

# Import GitHub client (optional)
try:
    from github_client import GitHubClient, GitHubError
    from github_utils import (
        github_pr_to_pr_summary,
        extract_pr_numbers_from_commits,
        get_unique_prs,
    )
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False
    GitHubClient = None
    GitHubError = None
    github_pr_to_pr_summary = None
    extract_pr_numbers_from_commits = None
    get_unique_prs = None


class GitError(RuntimeError):
    """Exception raised for Git-related errors."""
    pass


def get_repos_root() -> Path:
    """Get the root directory path for local repositories.

    Checks the REPOS_ROOT environment variable first. If not set, defaults
    to a 'repos' directory in the current working directory.

    Returns:
        Path: The resolved absolute path to the repositories root directory.
    """
    env = os.getenv("REPOS_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "repos").resolve()


def resolve_repo_path(block_ref: BlockRef) -> Path:
    """Resolve the local file system path for a repository.

    Args:
        block_ref: BlockRef containing the repository name to resolve.

    Returns:
        Path: The absolute path to the repository directory.

    Raises:
        GitError: If the repository path does not exist on the file system.
    """
    root = get_repos_root()
    repo_path = root  / block_ref.repo_name
    if not repo_path.exists():
        raise GitError(f"Repo path does not exist: {repo_path}")
    return repo_path


def run_git(args: List[str], repo_path: Path) -> str:
    """Execute a git command in the specified repository directory.

    Args:
        args: List of git command arguments (without the 'git' prefix).
        repo_path: Path to the repository directory where the command should run.

    Returns:
        str: The stdout output from the git command.

    Raises:
        GitError: If the git command fails (non-zero exit code).
    """
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
    """Read file contents at a specific git reference (branch, commit, etc.).

    Args:
        block_ref: BlockRef specifying the repository, ref, and file path.

    Returns:
        Tuple[List[str], int]: A tuple containing:
            - List of file lines (as strings)
            - Total number of lines in the file

    Raises:
        GitError: If the git command fails or the file cannot be read.
    """
    repo_path = resolve_repo_path(block_ref)
    spec = f"{block_ref.ref}:{block_ref.path}"
    output = run_git(["show", spec], repo_path)
    lines = output.splitlines()
    return lines, len(lines)


def guess_language_from_path(path: str) -> str | None:
    """Infer the programming language from a file path extension.

    Args:
        path: File path string to analyze.

    Returns:
        str | None: The detected language name (e.g., 'python', 'javascript')
            or None if the language cannot be determined from the extension.
    """
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
    """Retrieve a code block with surrounding context lines.

    Extracts the specified code block and includes additional lines above and
    below for context. Also detects the programming language from the file path.

    Args:
        block_ref: BlockRef specifying the code block to retrieve.
        context_lines: Number of lines to include above and below the block
            (default: 10).

    Returns:
        CodeContext: A model containing the code block, surrounding code,
            line numbers, total file lines, and detected language.

    Raises:
        GitError: If the line range is invalid or the file cannot be read.
    """
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
    """Parse git blame porcelain format output into BlameEntry objects.

    Parses the structured output from 'git blame --line-porcelain' command
    and converts it into a list of BlameEntry models with commit, author,
    and code information for each line.

    Args:
        output: Raw output string from git blame --line-porcelain command.
        block_ref: BlockRef used to associate entries with the code block.

    Returns:
        List[BlameEntry]: List of BlameEntry objects, one per line in the block.
    """
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
    """Get git blame information for a specific code block.

    Executes git blame to retrieve line-by-line authorship and commit
    information for the specified code block range.

    Args:
        block_ref: BlockRef specifying the repository, ref, file, and line range.

    Returns:
        List[BlameEntry]: List of BlameEntry objects with blame information
            for each line in the block.

    Raises:
        GitError: If the git blame command fails.
    """
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
    """Get complete blame block information for a code range.

    Wraps get_blame_entries to return a BlameBlock model containing all
    blame entries for the specified code block.

    Args:
        block_ref: BlockRef specifying the code block to analyze.

    Returns:
        BlameBlock: A model containing all blame entries for the block.

    Raises:
        GitError: If the git blame command fails.
    """
    entries = get_blame_entries(block_ref)
    return BlameBlock(block_ref=block_ref, entries=entries)


def get_commit_summaries_for_block(
    block_ref: BlockRef,
    max_commits: int = 10,
    include_prs: bool = True,
) -> Tuple[BlameBlock | None, List[CommitSummary]]:
    """Retrieve commit history for a code block.

    Gets blame information for the block, extracts unique commit SHAs,
    and fetches detailed commit information (author, date, message, diff)
    for up to max_commits distinct commits. Optionally fetches associated
    PR numbers from GitHub.

    Args:
        block_ref: BlockRef specifying the code block to analyze.
        max_commits: Maximum number of distinct commits to retrieve
            (default: 10).
        include_prs: Whether to fetch PR numbers from GitHub (default: True).

    Returns:
        Tuple[BlameBlock | None, List[CommitSummary]]: A tuple containing:
            - BlameBlock with all blame entries (or None if blame fails)
            - List of CommitSummary objects with commit details

    Raises:
        GitError: If git commands fail during execution.
    """
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

    # Try to fetch PR numbers from GitHub if available
    commit_to_pr_numbers: Dict[str, List[int]] = {}
    if include_prs and GITHUB_AVAILABLE:
        try:
            github_client = GitHubClient()
            commit_to_prs = github_client.get_prs_for_commits(
                owner=block_ref.repo_owner,
                repo=block_ref.repo_name,
                commit_shas=shas,
            )
            commit_to_pr_numbers = extract_pr_numbers_from_commits(commit_to_prs)
        except (GitHubError, Exception):
            # If GitHub API fails, continue without PR numbers
            pass

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

        # Get PR numbers for this commit
        pr_numbers = commit_to_pr_numbers.get(sha)
        if pr_numbers and len(pr_numbers) == 0:
            pr_numbers = None

        summaries.append(
            CommitSummary(
                sha=full_sha,
                author=author,
                author_email=author_email,
                date=date,
                message=message,
                diff_hunks_for_block=[diff_output],
                pr_numbers=pr_numbers,
            )
        )

    return blame_block, summaries


def build_history_context(
    block_ref: BlockRef,
    max_commits: int = 10,
    include_prs: bool = True,
    max_prs: int = 10,
) -> HistoryContext:
    """Build complete history context with blame and commit information.

    Aggregates git blame data and commit history for a code block into a
    single HistoryContext model. Optionally fetches PR discussions from GitHub.
    Handles errors gracefully by returning empty blame/commits/PRs if operations fail.

    Args:
        block_ref: BlockRef specifying the code block to analyze.
        max_commits: Maximum number of commits to include in the history
            (default: 10).
        include_prs: Whether to fetch PR discussions from GitHub (default: True).
        max_prs: Maximum number of PRs to include (default: 10).

    Returns:
        HistoryContext: A model containing blame information, commit summaries,
            and PR discussions.
    """
    try:
        blame_block, commits = get_commit_summaries_for_block(
            block_ref,
            max_commits=max_commits,
            include_prs=include_prs,
        )
    except GitError:
        blame_block = None
        commits = []

    # Fetch PR discussions if available
    prs: List[PRDiscussionSummary] = []
    if include_prs and GITHUB_AVAILABLE and commits:
        try:
            github_client = GitHubClient()
            
            # Get all commit SHAs
            commit_shas = [commit.sha for commit in commits]
            
            # Get PRs for commits
            commit_to_prs = github_client.get_prs_for_commits(
                owner=block_ref.repo_owner,
                repo=block_ref.repo_name,
                commit_shas=commit_shas,
            )
            
            # Get unique PRs
            unique_prs = get_unique_prs(commit_to_prs)
            
            # Convert to PRDiscussionSummary and fetch discussions
            for pr_data in unique_prs[:max_prs]:
                try:
                    pr_number = pr_data.get("number")
                    if pr_number:
                        # Fetch full discussion
                        discussion = github_client.get_pr_discussion(
                            owner=block_ref.repo_owner,
                            repo=block_ref.repo_name,
                            pr_number=pr_number,
                            include_reviews=True,
                            include_comments=True,
                            max_comments=20,
                        )
                        
                        # Convert to PRDiscussionSummary
                        pr_summary = github_pr_to_pr_summary(
                            pr_data=pr_data,
                            discussion_data=discussion,
                            max_comments=10,
                        )
                        prs.append(pr_summary)
                except (GitHubError, Exception):
                    # If we can't get PR discussion, skip it
                    continue
        except (GitHubError, Exception):
            # If GitHub API fails, continue without PRs
            pass

    return HistoryContext(
        block_ref=block_ref,
        blame=blame_block,
        commits=commits,
        prs=prs,
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
