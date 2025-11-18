from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Literal

from dotenv import load_dotenv
from openai import OpenAI

from models import BlockRef
from tools import (
    GetCodeContextInput,
    GetHistoryContextInput,
    GetLinearIssuesForBlockInput,
    SearchLinearIssuesInput,
    CreateLinearIssueInput,
    get_code_context_tool,
    get_history_context_tool,
    get_linear_issues_for_block_tool,
    search_linear_issues_tool,
    create_linear_issue_tool,
)

# Import Gemini client (optional)
try:
    from gemini_client import GeminiClient, GeminiError
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    GeminiClient = None
    GeminiError = None


load_dotenv()


class GitHistoryAgent:
    """Agent that uses LLM with tool calling to answer questions about code history.
    
    Supports both OpenAI and Google Gemini providers, with context caching for Gemini.
    """
    
    def __init__(
        self,
        provider: Literal["openai", "gemini"] = "openai",
        model: Optional[str] = None,
        use_context_caching: bool = True,
        cache_ttl_seconds: int = 3600,
    ):
        """Initialize the GitHistoryAgent with the specified provider.

        Args:
            provider: LLM provider to use ('openai' or 'gemini', default: 'openai').
            model: Model name to use. Defaults to provider-specific defaults:
                - OpenAI: 'gpt-4o-mini'
                - Gemini: 'gemini-1.5-pro'
            use_context_caching: Whether to use context caching for Gemini (default: True).
            cache_ttl_seconds: TTL for context caches in seconds (default: 3600).
        """
        self.provider = provider
        
        # Set default model based on provider
        if model is None:
            if provider == "openai":
                model = "gpt-4o-mini"
            elif provider == "gemini":
                model = "gemini-1.5-pro"
            else:
                raise ValueError(f"Unknown provider: {provider}")
        
        self.model = model
        
        # Initialize provider-specific clients
        if provider == "openai":
            self.client = OpenAI()
            self.gemini_client = None
        elif provider == "gemini":
            if not GEMINI_AVAILABLE:
                raise ImportError(
                    "Gemini client not available. Install google-generativeai: "
                    "pip install google-generativeai"
                )
            self.client = None
            self.gemini_client = GeminiClient(
                model=model,
                use_context_caching=use_context_caching,
                cache_ttl_seconds=cache_ttl_seconds,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        
        # Cache for storing context per block_ref (for Gemini caching)
        self._context_cache_keys: Dict[str, str] = {}

    def build_system_prompt(self) -> str:
        """Construct the system prompt for the LLM.

        Creates a prompt that instructs the LLM on its role as a code history
        assistant and how to use the available tools to answer questions.

        Returns:
            str: The system prompt string for the LLM.
        """
        return (
            "You are a code history assistant. "
            "You answer questions about a specific block of code. "
            "The backend will give you the repo, file path, and line range. "
            "When you need details, call the available tools to fetch:\n"
            "- The current code and its surrounding context\n"
            "- Git blame information and commit history for the block\n"
            "- GitHub PR discussions and reviews related to the code changes\n"
            "- Linear issues related to the code block\n"
            "- Search or create Linear issues for project management\n\n"
            "Use tools when needed instead of guessing. "
            "Reference line numbers, commits, and PRs when useful. "
            "You can also help create Linear issues for bugs, improvements, or tasks related to the code. "
            "When PR discussions are available, use them to provide context about why code was changed."
        )

    def _tool_definitions(self) -> List[Dict[str, Any]]:
        """Return tool definitions for OpenAI function calling.

        Defines the available tools that the LLM can call to retrieve information
        about code blocks and manage Linear issues.

        Returns:
            List[Dict[str, Any]]: List of tool definition dictionaries
                compatible with OpenAI's function calling API.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_code_context",
                    "description": (
                        "Fetch code and surrounding context for the current block of code. "
                        "The backend already knows which block is in focus; you only need to "
                        "choose how many lines of surrounding context to include."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "context_lines": {
                                "type": "integer",
                                "minimum": 0,
                                "default": 10,
                                "description": "Number of lines to include above and below the block.",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_history_context",
                    "description": (
                        "Fetch git blame and commit history for the current block of code. "
                        "The backend already knows which block is in focus; you only need to "
                        "choose how many distinct commits to include."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_commits": {
                                "type": "integer",
                                "minimum": 1,
                                "default": 10,
                                "description": "Maximum number of commits to include in the history.",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_linear_issues_for_block",
                    "description": (
                        "Find Linear issues related to the current code block. "
                        "Searches for issues that mention the repository, file path, or line numbers. "
                        "The backend already knows which block is in focus."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_id": {
                                "type": "string",
                                "description": "Optional team ID to filter issues by.",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 50,
                                "default": 10,
                                "description": "Maximum number of issues to return.",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_linear_issues",
                    "description": (
                        "Search for Linear issues by query, team, or state. "
                        "Use this to find existing issues or check if similar issues already exist."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query string (searches title and description).",
                            },
                            "team_id": {
                                "type": "string",
                                "description": "Optional team ID to filter by.",
                            },
                            "state": {
                                "type": "string",
                                "description": "Optional state name to filter by (e.g., 'In Progress', 'Done').",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 20,
                                "description": "Maximum number of issues to return.",
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_linear_issue",
                    "description": (
                        "Create a new Linear issue for tracking bugs, improvements, or tasks. "
                        "Use this when the user wants to create an issue related to the code block."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "team_id": {
                                "type": "string",
                                "description": "ID of the team to create the issue in (required).",
                            },
                            "title": {
                                "type": "string",
                                "description": "Issue title (required).",
                            },
                            "description": {
                                "type": "string",
                                "description": "Issue description. Include code block reference if relevant.",
                            },
                            "assignee_id": {
                                "type": "string",
                                "description": "Optional assignee ID.",
                            },
                            "state_id": {
                                "type": "string",
                                "description": "Optional state ID.",
                            },
                            "priority": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 4,
                                "description": "Priority (0=urgent, 1=high, 2=medium, 3=low, 4=none).",
                            },
                            "label_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional list of label IDs.",
                            }
                        },
                        "required": ["team_id", "title"],
                    },
                },
            },
        ]

    def _execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        block_ref: BlockRef,
    ) -> Dict[str, Any]:
        """Execute a tool call and return the results as a dictionary.

        Routes tool calls to the appropriate wrapper function and returns
        the results in a format suitable for the LLM.

        Args:
            name: Name of the tool to execute.
            arguments: Dictionary of arguments for the tool call.
            block_ref: BlockRef specifying the code block being analyzed.

        Returns:
            Dict[str, Any]: Dictionary representation of the tool result.

        Raises:
            ValueError: If the tool name is not recognized.
        """
        if name == "get_code_context":
            context_lines = arguments.get("context_lines", 10)
            result = get_code_context_tool(
                GetCodeContextInput(
                    block_ref=block_ref,
                    context_lines=context_lines,
                )
            )
            return result.model_dump()

        if name == "get_history_context":
            max_commits = arguments.get("max_commits", 10)
            result = get_history_context_tool(
                GetHistoryContextInput(
                    block_ref=block_ref,
                    max_commits=max_commits,
                )
            )
            return result.model_dump()

        if name == "get_linear_issues_for_block":
            team_id = arguments.get("team_id")
            limit = arguments.get("limit", 10)
            result = get_linear_issues_for_block_tool(
                GetLinearIssuesForBlockInput(
                    block_ref=block_ref,
                    team_id=team_id,
                    limit=limit,
                )
            )
            return result.model_dump()

        if name == "search_linear_issues":
            query = arguments.get("query")
            team_id = arguments.get("team_id")
            state = arguments.get("state")
            limit = arguments.get("limit", 20)
            result = search_linear_issues_tool(
                SearchLinearIssuesInput(
                    query=query,
                    team_id=team_id,
                    state=state,
                    limit=limit,
                )
            )
            # Convert list of issues to a format the LLM can understand
            return {"issues": [issue.model_dump() for issue in result]}

        if name == "create_linear_issue":
            team_id = arguments.get("team_id")
            title = arguments.get("title")
            description = arguments.get("description") or ""
            assignee_id = arguments.get("assignee_id")
            state_id = arguments.get("state_id")
            priority = arguments.get("priority")
            label_ids = arguments.get("label_ids")
            
            # Include code block reference in description
            code_ref = (
                f"\n\n**Related Code Block:**\n"
                f"Repository: {block_ref.repo_owner}/{block_ref.repo_name}\n"
                f"File: {block_ref.path}\n"
                f"Lines: {block_ref.start_line}-{block_ref.end_line}\n"
                f"Branch: {block_ref.ref}"
            )
            # Only add if not already present and description is not empty
            if code_ref not in description:
                description = description + code_ref if description else code_ref.strip()
            
            result = create_linear_issue_tool(
                CreateLinearIssueInput(
                    team_id=team_id,
                    title=title,
                    description=description,
                    assignee_id=assignee_id,
                    state_id=state_id,
                    priority=priority,
                    label_ids=label_ids,
                )
            )
            return result.model_dump()

        raise ValueError(f"Unknown tool: {name}")

    def answer_question(
        self,
        block_ref: BlockRef,
        question: str,
        use_cached_context: bool = True,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Answer a question about a specific code block using LLM with tool calling.

        This is the main method that orchestrates the interaction with the LLM.
        It sends the question along with the code block reference, allows the
        LLM to call tools as needed to gather context and history, and returns
        the final answer.

        For Gemini with caching enabled, this method will cache the code context
        and git history, then reuse it for subsequent questions about the same
        code block, significantly reducing costs and latency.

        Args:
            block_ref: BlockRef specifying the code block to analyze.
            question: The question to ask about the code block.
            use_cached_context: Whether to use cached context for Gemini (default: True).
            conversation_history: Optional list of previous messages in the conversation.
                Each message should be a dict with "role" ("user" or "assistant") and "content".

        Returns:
            str: The LLM's answer to the question, which may reference commits,
                authors, and implementation details based on the retrieved context.

        Raises:
            GitError: If git operations fail during tool execution.
            Exception: If the LLM API call fails or other errors occur.
        """
        if self.provider == "gemini" and use_cached_context:
            return self._answer_question_with_gemini_caching(block_ref, question, conversation_history)
        elif self.provider == "openai":
            return self._answer_question_with_openai(block_ref, question, conversation_history)
        else:
            return self._answer_question_with_gemini(block_ref, question, conversation_history)

    def _answer_question_with_openai(
        self,
        block_ref: BlockRef,
        question: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Answer question using OpenAI (original implementation)."""
        tools = self._tool_definitions()

        block_description = (
            "You are analyzing this specific block of code in a git repository.\n"
            f"repo_owner: {block_ref.repo_owner}\n"
            f"repo_name: {block_ref.repo_name}\n"
            f"ref: {block_ref.ref}\n"
            f"path: {block_ref.path}\n"
            f"lines: {block_ref.start_line}-{block_ref.end_line}\n\n"
            "Use the tools to fetch code and history for THIS block only."
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt()},
        ]
        
        # Add conversation history if provided
        if conversation_history:
            # Add a context message about previous conversation
            if len(conversation_history) > 0:
                messages.append({
                    "role": "system",
                    "content": (
                        "Previous conversation context:\n"
                        "The user has been asking questions about this code block. "
                        "Use the conversation history below to provide context-aware answers. "
                        "Reference previous questions and answers when relevant."
                    ),
                })
                # Add conversation history (limit to last 10 messages to avoid token limits)
                for msg in conversation_history[-10:]:
                    messages.append({
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    })
        
        messages.append({"role": "user", "content": block_description})
        messages.append({"role": "user", "content": question})

        while True:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                for tc in tool_calls:
                    name = tc.function.name
                    raw_args = tc.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        args = {}

                    result = self._execute_tool(name, args, block_ref)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": name,
                            "content": json.dumps(result),
                        }
                    )

                continue

            content = message.content or ""
            return content

    def _answer_question_with_gemini_caching(
        self,
        block_ref: BlockRef,
        question: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Answer question using Gemini with context caching.

        This method leverages Gemini's context caching to cache code context
        and git history, then reuses it for subsequent questions about the
        same code block.
        """
        # Generate cache key for this block_ref
        block_ref_key = f"{block_ref.repo_owner}/{block_ref.repo_name}:{block_ref.path}:{block_ref.start_line}-{block_ref.end_line}"
        block_ref_dict = block_ref.model_dump()

        # Check if we have a cached context for this block
        cache_key = self._context_cache_keys.get(block_ref_key)

        # If no cache exists, fetch context and create cache
        if not cache_key:
            # Fetch code context and history context upfront
            code_context = None
            history_context = None

            try:
                # Get code context (default: 10 lines of context)
                code_context_result = get_code_context_tool(
                    GetCodeContextInput(block_ref=block_ref, context_lines=10)
                )
                code_context = code_context_result.model_dump()

                # Get history context (default: 10 commits)
                history_context_result = get_history_context_tool(
                    GetHistoryContextInput(block_ref=block_ref, max_commits=10)
                )
                history_context = history_context_result.model_dump()
            except Exception as e:
                # If context fetching fails, fall back to non-cached approach
                return self._answer_question_with_gemini(block_ref, question)

            # Create cache with the context
            system_prompt = self.build_system_prompt()
            cache_key = self.gemini_client.create_context_cache(
                block_ref_dict=block_ref_dict,
                system_prompt=system_prompt,
                code_context=code_context,
                history_context=history_context,
            )

            if cache_key:
                self._context_cache_keys[block_ref_key] = cache_key

        # Use cached context to answer the question
        if cache_key:
            try:
                # Convert tools to Gemini format (simplified for now)
                # Note: Gemini function calling format is different from OpenAI
                tools = None  # TODO: Convert tools to Gemini format

                # Add conversation history to question if available
                enhanced_question = question
                if conversation_history:
                    history_text = "\n\nPrevious conversation:\n"
                    for msg in conversation_history[-5:]:  # Last 5 messages
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        history_text += f"{role.capitalize()}: {content}\n"
                    enhanced_question = history_text + f"\nCurrent question: {question}"

                response = self.gemini_client.chat_with_cached_context(
                    cache_key=cache_key,
                    user_question=enhanced_question,
                    tools=tools,
                )
                return response
            except Exception as e:
                # If cached context fails, fall back to implicit caching
                return self._answer_question_with_gemini_implicit(
                    block_ref, question, code_context, history_context, conversation_history
                )

        # Fallback to non-cached approach
        return self._answer_question_with_gemini(block_ref, question, conversation_history)

    def _answer_question_with_gemini_implicit(
        self,
        block_ref: BlockRef,
        question: str,
        code_context: Optional[Dict[str, Any]] = None,
        history_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Answer question using Gemini with implicit caching (common prefix)."""
        system_prompt = self.build_system_prompt()

        # If context not provided, fetch it
        if not code_context:
            try:
                code_context_result = get_code_context_tool(
                    GetCodeContextInput(block_ref=block_ref, context_lines=10)
                )
                code_context = code_context_result.model_dump()
            except Exception:
                code_context = None

        if not history_context:
            try:
                history_context_result = get_history_context_tool(
                    GetHistoryContextInput(block_ref=block_ref, max_commits=10)
                )
                history_context = history_context_result.model_dump()
            except Exception:
                history_context = None

        response = self.gemini_client.chat_with_implicit_caching(
            system_prompt=system_prompt,
            code_context=code_context,
            history_context=history_context,
            user_question=question,
            tools=None,  # TODO: Convert tools to Gemini format
        )
        return response

    def _answer_question_with_gemini(
        self,
        block_ref: BlockRef,
        question: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Answer question using Gemini without caching (fallback)."""
        return self._answer_question_with_gemini_implicit(block_ref, question, None, None, conversation_history)