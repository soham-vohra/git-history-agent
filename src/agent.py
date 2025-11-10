from __future__ import annotations

import json
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

from models import BlockRef
from tools import (
    GetCodeContextInput,
    GetHistoryContextInput,
    get_code_context_tool,
    get_history_context_tool,
)


load_dotenv()


class GitHistoryAgent:
    """Agent that uses LLM with tool calling to answer questions about code history."""
    
    def __init__(self, model: str = "gpt-4.1-mini"):
        """Initialize the GitHistoryAgent with an OpenAI client.

        Args:
            model: The OpenAI model name to use for chat completions
                (default: "gpt-4.1-mini").
        """
        self.client = OpenAI()
        self.model = model

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
            "- Git blame information and commit history for the block.\n\n"
            "Use tools when needed instead of guessing. "
            "Reference line numbers and commits when useful."
        )

    def _tool_definitions(self) -> List[Dict[str, Any]]:
        """Return tool definitions for OpenAI function calling.

        Defines the available tools (get_code_context and get_history_context)
        that the LLM can call to retrieve information about code blocks.

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
            name: Name of the tool to execute ('get_code_context' or
                'get_history_context').
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

        raise ValueError(f"Unknown tool: {name}")

    def answer_question(
        self,
        block_ref: BlockRef,
        question: str,
    ) -> str:
        """Answer a question about a specific code block using LLM with tool calling.

        This is the main method that orchestrates the interaction with the LLM.
        It sends the question along with the code block reference, allows the
        LLM to call tools as needed to gather context and history, and returns
        the final answer.

        Args:
            block_ref: BlockRef specifying the code block to analyze.
            question: The question to ask about the code block.

        Returns:
            str: The LLM's answer to the question, which may reference commits,
                authors, and implementation details based on the retrieved context.

        Raises:
            GitError: If git operations fail during tool execution.
            Exception: If the LLM API call fails or other errors occur.
        """
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
            {"role": "user", "content": block_description},
            {"role": "user", "content": question},
        ]

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