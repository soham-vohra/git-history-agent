from __future__ import annotations

import os
import hashlib
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from dotenv import load_dotenv

load_dotenv()


class GeminiError(RuntimeError):
    """Exception raised for Gemini API errors."""
    pass


class ContextCache:
    """Manages context caching for Gemini API.
    
    This class handles creating and managing cached contexts for code blocks,
    allowing reuse of large code context and git history across multiple queries.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize the context cache manager.

        Args:
            ttl_seconds: Time to live for caches in seconds (default: 1 hour).
        """
        self.ttl_seconds = ttl_seconds
        self._cache_store: Dict[str, Dict[str, Any]] = {}
        self._cache_metadata: Dict[str, datetime] = {}

    def _generate_cache_key(self, block_ref_dict: Dict[str, Any], context_type: str) -> str:
        """Generate a unique cache key for a block reference and context type.

        Args:
            block_ref_dict: Dictionary representation of BlockRef.
            context_type: Type of context ('code', 'history', 'combined').

        Returns:
            str: Unique cache key.
        """
        key_data = {
            **block_ref_dict,
            "context_type": context_type,
        }
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()

    def create_cache(
        self,
        cache_key: str,
        content: str,
        display_name: Optional[str] = None,
    ) -> str:
        """Create a context cache with the given content.

        Args:
            cache_key: Unique key for the cache.
            content: Content to cache.
            display_name: Optional display name for the cache.

        Returns:
            str: Cache key (for reference in API calls).
        """
        # Store cache locally with metadata
        self._cache_store[cache_key] = {
            "content": content,
            "display_name": display_name or f"cache_{cache_key[:8]}",
            "created_at": datetime.now(),
        }
        self._cache_metadata[cache_key] = datetime.now()
        return cache_key

    def get_cache(self, cache_key: str) -> Optional[str]:
        """Retrieve cached content if it exists and hasn't expired.

        Args:
            cache_key: Cache key to retrieve.

        Returns:
            str: Cached content if available and not expired, None otherwise.
        """
        if cache_key not in self._cache_store:
            return None

        # Check if cache has expired
        created_at = self._cache_metadata.get(cache_key)
        if created_at:
            age = datetime.now() - created_at
            if age.total_seconds() > self.ttl_seconds:
                # Cache expired, remove it
                self._cache_store.pop(cache_key, None)
                self._cache_metadata.pop(cache_key, None)
                return None

        return self._cache_store[cache_key]["content"]

    def delete_cache(self, cache_key: str) -> bool:
        """Delete a cache by key.

        Args:
            cache_key: Cache key to delete.

        Returns:
            bool: True if cache was deleted, False if it didn't exist.
        """
        existed = cache_key in self._cache_store
        self._cache_store.pop(cache_key, None)
        self._cache_metadata.pop(cache_key, None)
        return existed

    def cleanup_expired(self) -> int:
        """Remove all expired caches.

        Returns:
            int: Number of caches removed.
        """
        now = datetime.now()
        expired_keys = [
            key
            for key, created_at in self._cache_metadata.items()
            if (now - created_at).total_seconds() > self.ttl_seconds
        ]
        for key in expired_keys:
            self.delete_cache(key)
        return len(expired_keys)


class GeminiClient:
    """Client for interacting with Google's Gemini API with context caching support."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-pro",
        use_context_caching: bool = True,
        cache_ttl_seconds: int = 3600,
    ):
        """Initialize the Gemini client.

        Args:
            api_key: Gemini API key. If not provided, will try to get from
                GEMINI_API_KEY environment variable.
            model: Gemini model name (default: "gemini-1.5-pro").
            use_context_caching: Whether to use context caching (default: True).
            cache_ttl_seconds: TTL for context caches in seconds (default: 3600).
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise GeminiError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable."
            )

        genai.configure(api_key=self.api_key)
        self.model_name = model
        self.use_context_caching = use_context_caching
        self.context_cache = ContextCache(ttl_seconds=cache_ttl_seconds) if use_context_caching else None
        
        # Configure safety settings
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        }

    def _prepare_content_for_cache(
        self,
        system_prompt: str,
        code_context: Optional[Dict[str, Any]] = None,
        history_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Prepare content for caching by combining system prompt and contexts.

        Args:
            system_prompt: System prompt for the LLM.
            code_context: Optional code context dictionary.
            history_context: Optional git history context dictionary (includes PRs).

        Returns:
            str: Formatted content string for caching.
        """
        parts = [system_prompt]

        if code_context:
            code_block = code_context.get("code_block", "")
            surrounding_code = code_context.get("surrounding_code", "")
            language = code_context.get("language", "unknown")
            
            parts.append(f"\n\n## Code Context (Language: {language})")
            parts.append(f"\n### Code Block:\n```{language}\n{code_block}\n```")
            if surrounding_code and surrounding_code != code_block:
                parts.append(f"\n### Surrounding Context:\n```{language}\n{surrounding_code}\n```")

        if history_context:
            commits = history_context.get("commits", [])
            blame = history_context.get("blame")
            prs = history_context.get("prs", [])
            
            if blame and blame.get("entries"):
                parts.append("\n\n## Git Blame Information")
                for entry in blame["entries"][:10]:  # Limit to first 10 entries
                    parts.append(
                        f"Line {entry.get('line')}: {entry.get('code', '')[:50]}... "
                        f"(Commit: {entry.get('commit', '')[:8]}, Author: {entry.get('author', 'Unknown')})"
                    )

            if commits:
                parts.append("\n\n## Commit History")
                for commit in commits[:5]:  # Limit to first 5 commits
                    commit_line = (
                        f"Commit {commit.get('sha', '')[:8]}: {commit.get('message', '')[:100]} "
                        f"(Author: {commit.get('author', 'Unknown')}, Date: {commit.get('date', 'Unknown')})"
                    )
                    # Add PR numbers if available
                    pr_numbers = commit.get("pr_numbers")
                    if pr_numbers:
                        pr_nums = ", ".join([f"#{num}" for num in pr_numbers[:3]])
                        commit_line += f" [PRs: {pr_nums}]"
                    parts.append(commit_line)

            if prs:
                parts.append("\n\n## Pull Request Discussions")
                for pr in prs[:5]:  # Limit to first 5 PRs
                    pr_line = f"PR #{pr.get('number')}: {pr.get('title', '')[:80]}"
                    pr_state = pr.get("state", "unknown")
                    if pr_state:
                        pr_line += f" ({pr_state})"
                    parts.append(pr_line)
                    
                    # Add PR summary
                    summary = pr.get("summary", "")
                    if summary:
                        parts.append(f"  Summary: {summary[:200]}...")
                    
                    # Add key comments
                    key_comments = pr.get("key_comments", [])
                    if key_comments:
                        parts.append(f"  Key Comments ({len(key_comments)}):")
                        for comment in key_comments[:3]:  # Limit to 3 comments
                            parts.append(f"    - {comment[:150]}...")

        return "\n".join(parts)

    def create_context_cache(
        self,
        block_ref_dict: Dict[str, Any],
        system_prompt: str,
        code_context: Optional[Dict[str, Any]] = None,
        history_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a context cache for a code block.

        Args:
            block_ref_dict: Dictionary representation of BlockRef.
            system_prompt: System prompt for the LLM.
            code_context: Optional code context dictionary.
            history_context: Optional git history context dictionary.

        Returns:
            str: Cache key if caching is enabled, None otherwise.
        """
        if not self.use_context_caching or not self.context_cache:
            return None

        # Prepare content for caching
        content = self._prepare_content_for_cache(
            system_prompt=system_prompt,
            code_context=code_context,
            history_context=history_context,
        )

        # Generate cache key
        cache_key = self.context_cache._generate_cache_key(block_ref_dict, "combined")

        # Create cache
        display_name = f"{block_ref_dict.get('repo_name', 'repo')}_{block_ref_dict.get('path', 'file')}_{block_ref_dict.get('start_line', 0)}"
        self.context_cache.create_cache(cache_key, content, display_name)

        return cache_key

    def chat_with_cached_context(
        self,
        cache_key: Optional[str],
        user_question: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Send a chat message using locally cached context.

        This method uses the local cache to retrieve context and structures
        the prompt for Gemini's implicit caching (common prefix caching).

        Args:
            cache_key: Optional cache key to reference cached context.
            user_question: User's question.
            tools: Optional list of tool definitions for function calling.

        Returns:
            str: Model's response.

        Raises:
            GeminiError: If the API call fails.
        """
        try:
            # Get cached content if available
            cached_content = None
            if cache_key and self.context_cache:
                cached_content = self.context_cache.get_cache(cache_key)

            # Build prompt with common prefix (for implicit caching)
            if cached_content:
                # Structure: common prefix (cached) + variable part (question)
                # Gemini will automatically cache the common prefix
                prompt = f"{cached_content}\n\n## User Question\n{user_question}"
            else:
                # No cache available, use question only
                prompt = user_question

            # Get the model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings=list(self.safety_settings.items()),
                tools=tools,
            )

            # Generate content
            # Gemini's implicit caching will automatically cache common prefixes
            response = model.generate_content(prompt)

            # Extract text response
            if response.text:
                return response.text
            else:
                return "No response generated."

        except Exception as e:
            raise GeminiError(f"Gemini API error: {e}")

    def chat_with_implicit_caching(
        self,
        system_prompt: str,
        code_context: Optional[Dict[str, Any]],
        history_context: Optional[Dict[str, Any]],
        user_question: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Send a chat message using implicit caching (common prefix caching).

        This method structures the prompt so that Gemini's implicit caching
        can automatically cache the common parts (system prompt, code context, history).
        When multiple questions are asked about the same code block, Gemini will
        automatically cache the common prefix and only charge for the variable part.

        Key benefits:
        - Reduced costs: Cached tokens are billed at a reduced rate
        - Faster responses: Less data to process
        - Automatic: No manual cache management needed

        Args:
            system_prompt: System prompt for the LLM.
            code_context: Optional code context dictionary.
            history_context: Optional git history context dictionary.
            user_question: User's question (variable part, goes at the end).

        Returns:
            str: Model's response.

        Raises:
            GeminiError: If the API call fails.
        """
        try:
            # Build the full prompt with common prefix (for implicit caching)
            # IMPORTANT: Common content goes FIRST, variable content (question) goes LAST
            # This allows Gemini to automatically cache the common prefix
            prompt_parts = []

            # 1. System prompt (common)
            prompt_parts.append(system_prompt)

            # 2. Code context (common)
            if code_context:
                code_block = code_context.get("code_block", "")
                surrounding_code = code_context.get("surrounding_code", "")
                language = code_context.get("language", "unknown")
                
                prompt_parts.append(f"\n\n## Code Context (Language: {language})")
                prompt_parts.append(f"### Code Block:\n```{language}\n{code_block}\n```")
                if surrounding_code and surrounding_code != code_block:
                    prompt_parts.append(f"\n### Surrounding Context:\n```{language}\n{surrounding_code}\n```")

            # 3. Git history context (common)
            if history_context:
                commits = history_context.get("commits", [])
                blame = history_context.get("blame")
                prs = history_context.get("prs", [])
                
                if blame and blame.get("entries"):
                    prompt_parts.append("\n\n## Git Blame Information")
                    for entry in blame["entries"][:10]:  # Limit to first 10 entries
                        prompt_parts.append(
                            f"Line {entry.get('line')}: {entry.get('code', '')[:60]}... "
                            f"(Commit: {entry.get('commit', '')[:8]}, Author: {entry.get('author', 'Unknown')})"
                        )

                if commits:
                    prompt_parts.append("\n\n## Commit History")
                    for commit in commits[:5]:  # Limit to first 5 commits
                        commit_line = (
                            f"Commit {commit.get('sha', '')[:8]}: {commit.get('message', '')[:100]} "
                            f"(Author: {commit.get('author', 'Unknown')}, Date: {commit.get('date', 'Unknown')})"
                        )
                        # Add PR numbers if available
                        pr_numbers = commit.get("pr_numbers")
                        if pr_numbers:
                            pr_nums = ", ".join([f"#{num}" for num in pr_numbers[:3]])
                            commit_line += f" [PRs: {pr_nums}]"
                        prompt_parts.append(commit_line)

                if prs:
                    prompt_parts.append("\n\n## Pull Request Discussions")
                    for pr in prs[:5]:  # Limit to first 5 PRs
                        pr_line = f"PR #{pr.get('number')}: {pr.get('title', '')[:80]}"
                        pr_state = pr.get("state", "unknown")
                        if pr_state:
                            pr_line += f" ({pr_state})"
                        prompt_parts.append(pr_line)
                        
                        # Add PR summary
                        summary = pr.get("summary", "")
                        if summary:
                            prompt_parts.append(f"  Summary: {summary[:200]}")
                        
                        # Add key comments
                        key_comments = pr.get("key_comments", [])
                        if key_comments:
                            for comment in key_comments[:2]:  # Limit to 2 comments per PR
                                prompt_parts.append(f"  - {comment[:150]}")

            # 4. User question (VARIABLE - goes at the end for implicit caching)
            prompt_parts.append(f"\n\n## User Question\n{user_question}")

            full_prompt = "\n".join(prompt_parts)

            # Get the model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                safety_settings=list(self.safety_settings.items()),
                tools=tools,
            )

            # Generate content
            # Gemini will automatically cache the common prefix (everything before the question)
            # Subsequent requests with the same prefix will use the cache
            response = model.generate_content(full_prompt)

            if response.text:
                return response.text
            else:
                return "No response generated."

        except Exception as e:
            raise GeminiError(f"Gemini API error: {e}")


__all__ = ["GeminiClient", "GeminiError", "ContextCache"]

