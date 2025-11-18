

# Git History Agent

## Overview

Git History Agent is an LLM-powered backend designed to provide rich context and historical insights about code in Git repositories. It fetches code context, blame information, commit history, and PR discussions, enabling context-aware developer assistants and advanced code graph visualizations

## Features

- **Retrieve code block context:** Get surrounding lines for any code block.
- **Fetch git blame and commit history:** Obtain author and commit details for specific code regions.
- **GitHub PR discussions:** Fetch pull request discussions, reviews, and comments related to code changes.
- **Multi-LLM support:** Use OpenAI GPT or Google Gemini models.
- **Gemini Context Caching:** Reduce costs and latency by caching code context and git history (Gemini only).
- **OpenAI GPT tool-calling:** Analyze code and explain implementation details using LLMs.
- **FastAPI `/chat` endpoint:** Query an LLM with repository-aware questions.
- **Linear integration:** Search, create, and manage Linear issues directly from code analysis.
- **GitHub integration:** Access PR discussions and reviews to understand code changes.
- **Designed for integration:** Easily connect with MCP or visualization tools for seamless developer experiences.

## Project Structure

- `models.py`: Pydantic models for BlockRef, CodeContext, HistoryContext, PRDiscussionSummary, LinearIssue, and related data structures.
- `git_core.py`: Core Git logic, including blame, context extraction, commit history, and GitHub PR integration.
- `github_client.py`: GitHub API client for fetching PRs, discussions, and reviews.
- `github_utils.py`: Utility functions for converting GitHub API responses to our models.
- `gemini_client.py`: Gemini API client with context caching support.
- `linear_client.py`: Linear API client for GraphQL queries and mutations.
- `tools.py`: Wraps `git_core`, `github_client`, and `linear_client` functions as callable tools for LLMs.
- `agent.py`: Orchestrates LLM tool-calling (OpenAI and Gemini), reasoning, and response synthesis.
- `llm_client.py`: FastAPI application exposing the `/chat`, Linear, and GitHub API endpoints.
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
   pip install -r requirements-test.txt  # For testing
   ```

4. **Set up environment variables:**
   Create a `.env` file in the project root:
   ```bash
   OPENAI_API_KEY=your-openai-api-key
   REPO_ROOT=/path/to/local/repo
   LINEAR_API_KEY=your-linear-api-key  # Optional: for Linear integration
   GITHUB_API_KEY=your-github-api-key  # Optional: for GitHub PR integration (recommended for higher rate limits)
   
   # Gemini with Context Caching (Optional)
   LLM_PROVIDER=gemini  # Use 'openai' or 'gemini' (default: openai)
   GEMINI_API_KEY=your-gemini-api-key  # Required if using Gemini
   USE_CONTEXT_CACHING=true  # Enable context caching for Gemini (default: true)
   CACHE_TTL_SECONDS=3600  # Cache TTL in seconds (default: 3600)
   ```

   **Getting API Keys:**
   - **OpenAI**: Get your API key from [OpenAI Platform](https://platform.openai.com/api-keys)
   - **Gemini**: Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - **Linear**: Go to Linear Settings → API → Personal API Keys
   - **GitHub**: Create a Personal Access Token at [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens)
     - Required scopes: `public_repo` (for public repos) or `repo` (for private repos)
     - Note: GitHub API works without a key for public repos, but has strict rate limits (60 requests/hour)
     - With API key: 5,000 requests/hour
   
   **Note**: You can use either OpenAI or Gemini. Linear and GitHub integrations are optional.

## Running the API Server

To start the FastAPI backend:
```bash
cd src
uvicorn llm_client:app --reload
```
Visit the Swagger UI at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to test the endpoints.

## Testing

### Quick Test

Run the manual test script to verify everything works:
```bash
python test_manual.py
```

### Run All Tests

```bash
pytest
```

### Run Tests with Coverage

```bash
pytest --cov=src --cov-report=html
```

### Run Specific Tests

```bash
# Test models
pytest tests/test_models.py

# Test Linear integration
pytest tests/test_linear_client.py

# Test Gemini integration
pytest tests/test_gemini_client.py

# Test API endpoints
pytest tests/test_api.py
```

See [TESTING.md](TESTING.md) for detailed testing instructions.

### Available Endpoints

- **POST `/chat`**: Query the LLM about code blocks (includes GitHub PR and Linear integration in agent tools)
  - Supports optional `session_id` for conversation memory
- **POST `/chat/sessions`**: Create a new conversation session
- **GET `/chat/sessions/{session_id}`**: Get conversation history for a session
- **DELETE `/chat/sessions/{session_id}`**: Delete a conversation session
- **GET `/chat/sessions`**: Get statistics about active sessions
- **GET `/linear/teams`**: Get all Linear teams
- **GET `/linear/issues/{issue_id}`**: Get a specific Linear issue
- **POST `/linear/issues/search`**: Search for Linear issues
- **POST `/linear/issues`**: Create a new Linear issue
- **POST `/linear/issues/{issue_id}/comments`**: Add a comment to a Linear issue
- **GET `/github/repos/{owner}/{repo}/pulls/{pr_number}`**: Get a specific GitHub PR
- **POST `/github/repos/{owner}/{repo}/pulls/search`**: Search for GitHub PRs
- **POST `/github/repos/{owner}/{repo}/commits/prs`**: Get PRs for commit SHAs
- **GET `/github/repos/{owner}/{repo}/pulls/{pr_number}/discussion`**: Get PR discussion with reviews and comments

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

## Linear Integration

The agent can now interact with Linear to manage issues related to code blocks. The LLM can:

- **Search for Linear issues** related to a code block
- **Create Linear issues** for bugs, improvements, or tasks
- **Link code blocks to Linear issues** automatically when creating issues

### Example: Creating a Linear Issue via Chat

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
  "question": "Create a Linear issue for refactoring this code block. Team ID: abc123"
}
```

The agent will automatically:
1. Analyze the code block
2. Create a Linear issue with the code block reference in the description
3. Return the created issue information

### Linear API Endpoints

You can also use the Linear endpoints directly:

**Search for issues:**
```bash
curl -X POST "http://127.0.0.1:8000/linear/issues/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "bug", "team_id": "abc123", "limit": 10}'
```

**Create an issue:**
```bash
curl -X POST "http://127.0.0.1:8000/linear/issues" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "abc123",
    "title": "Fix bug in utils.py",
    "description": "Issue description here",
    "priority": 1
  }'
```

## GitHub PR Integration

Git History Agent now integrates with GitHub to fetch PR discussions, reviews, and comments related to code changes. This provides valuable context about why code was changed and what discussions happened during code review.

### Features

- **Automatic PR Discovery**: Finds PRs associated with commits in a code block
- **PR Discussions**: Fetches PR descriptions, reviews, and comments
- **Review Context**: Includes code review feedback and concerns
- **Commit Linking**: Links commits to their associated PRs
- **Rich Context**: Provides full PR discussion history for better code understanding

### How It Works

1. **When analyzing a code block**, the agent:
   - Fetches git commit history for the code block
   - Searches GitHub for PRs containing those commits
   - Fetches PR discussions, reviews, and comments
   - Includes PR context in the analysis

2. **The agent can now answer questions like**:
   - "Why was this code changed?" → Answers from PR discussions
   - "What were the review concerns?" → Review comments and feedback
   - "Who approved this change?" → PR review history
   - "What issues were discussed?" → PR comments and discussions

### Example Usage

```json
{
  "block_ref": {
    "repo_owner": "facebook",
    "repo_name": "react",
    "ref": "main",
    "path": "src/react.js",
    "start_line": 10,
    "end_line": 30
  },
  "question": "Why was this code changed? What were the concerns in the PR?"
}
```

The agent will automatically:
1. Fetch commit history for the code block
2. Find associated PRs on GitHub
3. Retrieve PR discussions and reviews
4. Provide context about why the code was changed

### GitHub API Endpoints

**Get PR for commits:**
```bash
curl -X POST "http://127.0.0.1:8000/github/repos/facebook/react/commits/prs" \
  -H "Content-Type: application/json" \
  -d '{"commit_shas": ["abc123", "def456"]}'
```

**Get PR discussion:**
```bash
curl "http://127.0.0.1:8000/github/repos/facebook/react/pulls/123/discussion"
```

**Search PRs:**
```bash
curl -X POST "http://127.0.0.1:8000/github/repos/facebook/react/pulls/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "bug fix", "state": "closed", "limit": 10}'
```

### Rate Limits

- **Without API key**: 60 requests/hour (GitHub's unauthenticated limit)
- **With API key**: 5,000 requests/hour
- **Recommendation**: Set `GITHUB_API_KEY` for production use

## Future Roadmap

- ✅ GitHub API integration for PR discussions and reviews (Completed!)
- Extend MCP server for broader LLM ecosystem interoperability
- Implement a repository cloning and caching pipeline
- Integrate with frontend graph visualization tools for code context navigation
- Enhance Linear issue linking with automatic detection from commit messages

## Gemini Context Caching

Git History Agent supports Google Gemini with **context caching**, which significantly reduces costs and improves latency when analyzing the same code blocks multiple times.

### How It Works

1. **First Request**: When you ask a question about a code block, the agent:
   - Fetches the code context and git history
   - Structures the prompt with common content (code, history) at the beginning
   - Sends the full prompt to Gemini
   - Gemini automatically caches the common prefix

2. **Subsequent Requests**: When you ask another question about the same code block:
   - The agent reuses the cached context
   - Only sends the new question (variable part)
   - Gemini uses the cached prefix, reducing tokens processed
   - **Result**: Lower costs and faster responses

### Benefits

- **Cost Savings**: Cached tokens are billed at a reduced rate (up to 75% cheaper)
- **Faster Responses**: Less data to process means lower latency
- **Automatic**: No manual cache management needed
- **Perfect for Code Analysis**: Multiple questions about the same code block are common

### Example Usage

```python
from agent import GitHistoryAgent
from models import BlockRef

# Initialize with Gemini and context caching
agent = GitHistoryAgent(
    provider="gemini",
    use_context_caching=True,
    cache_ttl_seconds=3600,  # Cache for 1 hour
)

block_ref = BlockRef(
    repo_owner="soham-vohra",
    repo_name="final_project",
    ref="main",
    path="src/core/utils.py",
    start_line=10,
    end_line=30,
)

# First question - fetches context and creates cache
answer1 = agent.answer_question(
    block_ref=block_ref,
    question="Why was this code implemented this way?",
)

# Second question - uses cached context (faster, cheaper)
answer2 = agent.answer_question(
    block_ref=block_ref,
    question="What are the potential issues with this implementation?",
)
```

### Configuration

Set these environment variables to use Gemini with context caching:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-gemini-api-key
USE_CONTEXT_CACHING=true
CACHE_TTL_SECONDS=3600  # Cache expires after 1 hour
```

### When to Use Context Caching

Context caching is most beneficial when:
- Analyzing the same code block multiple times
- Asking multiple questions about a specific function or module
- Running batch analyses on code repositories
- Building interactive code analysis tools

### Cost Comparison

**Without Caching** (each request):
- System prompt: ~200 tokens
- Code context: ~500-2000 tokens
- Git history: ~300-1000 tokens
- Question: ~50 tokens
- **Total per request**: ~1050-3250 tokens

**With Caching** (subsequent requests):
- Cached content: ~1050-3250 tokens (billed at reduced rate)
- Question only: ~50 tokens
- **Savings**: Up to 75% on cached tokens

For 10 questions about the same code block:
- **Without caching**: ~10,500-32,500 tokens
- **With caching**: ~1,050-3,250 tokens (cached) + 500 tokens (questions) = ~1,550-3,750 tokens
- **Savings**: ~85-90% reduction in token usage
