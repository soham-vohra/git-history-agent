

# Git History Agent

## Overview

Git History Agent is an LLM-powered backend designed to provide rich context and historical insights about code in Git repositories. It fetches code context, blame information, commit history, and PR discussions, enabling context-aware developer assistants and advanced code graph visualizations

## Features

- **Retrieve code block context:** Get surrounding lines for any code block.
- **Fetch git blame and commit history:** Obtain author and commit details for specific code regions.
- **OpenAI GPT tool-calling:** Analyze code and explain implementation details using LLMs.
- **FastAPI `/chat` endpoint:** Query an LLM with repository-aware questions.
- **Designed for integration:** Easily connect with MCP or visualization tools for seamless developer experiences.

## Project Structure

- `models.py`: Pydantic models for BlockRef, CodeContext, HistoryContext, and related data structures.
- `git_core.py`: Core Git logic, including blame, context extraction, and commit history.
- `tools.py`: Wraps `git_core` functions as callable tools for LLMs.
- `agent.py`: Orchestrates OpenAI GPT tool-calling, reasoning, and response synthesis.
- `llm_client.py`: FastAPI application exposing the `/chat` API endpoint.
- `mcp_git_server.py`: MCP-compatible server exposing git tools over stdio for LLM ecosystem integration.

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/git-history-agent.git
   cd git-history-agent
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   Create a `.env` file in the project root:
   ```bash
   OPENAI_API_KEY=your-openai-api-key
   REPO_ROOT=/path/to/local/repo
   ```

## Running the API Server

To start the FastAPI backend:
```bash
uvicorn llm_client:app --reload --app-dir src
```
Visit the Swagger UI at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to test the `/chat` endpoint.

## Example Request

```json
{
  "block_ref": {
    "repo_owner": "soham-vohra",
    "repo_name": "final_project",
    "ref": "main",
    "path": "src/core/utils.py",
    "start_line": 10,
    "end_line": 30
  },
  "question": "Why was this logic implemented this way?"
}
```

## Example Response

```json
{
  "answer": "This code handles edge cases in data parsing added in commit a1b2c3d4 by John Doe, optimizing for speed."
}
```

## Future Roadmap

- Add GitHub API integration for PR discussions and reviews
- Extend MCP server for broader LLM ecosystem interoperability
- Implement a repository cloning and caching pipeline
- Integrate with frontend graph visualization tools for code context navigation
