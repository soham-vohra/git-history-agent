# Testing Guide

This guide explains how to test the Git History Agent to ensure everything works properly.

## Quick Start

### 1. Install Test Dependencies

```bash
pip install -r requirements-test.txt
```

### 2. Run All Tests

```bash
pytest
```

### 3. Run Tests with Coverage

```bash
pytest --cov=src --cov-report=html
```

### 4. Run Specific Test Files

```bash
pytest tests/test_models.py
pytest tests/test_linear_client.py
pytest tests/test_gemini_client.py
pytest tests/test_agent.py
pytest tests/test_api.py
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── test_models.py           # Tests for data models
├── test_linear_client.py    # Tests for Linear API client
├── test_gemini_client.py    # Tests for Gemini client and caching
├── test_tools.py            # Tests for tool functions
├── test_agent.py            # Tests for GitHistoryAgent
└── test_api.py              # Tests for FastAPI endpoints
```

## Manual Testing

### 1. Test Linear Integration

#### Prerequisites
- Set `LINEAR_API_KEY` in your `.env` file
- Have access to a Linear workspace

#### Test Steps

1. **Test Linear Client**:
   ```python
   from linear_client import LinearClient
   
   client = LinearClient()
   teams = client.get_teams()
   print(f"Found {len(teams)} teams")
   ```

2. **Test Search Issues**:
   ```python
   issues = client.search_issues(query="bug", limit=10)
   print(f"Found {len(issues)} issues")
   ```

3. **Test Create Issue** (be careful - creates real issue):
   ```python
   issue = client.create_issue(
       team_id="your-team-id",
       title="Test Issue",
       description="This is a test issue",
   )
   print(f"Created issue: {issue['identifier']}")
   ```

#### Test via API

```bash
# Get teams
curl -X GET "http://127.0.0.1:8000/linear/teams" \
  -H "Content-Type: application/json"

# Search issues
curl -X POST "http://127.0.0.1:8000/linear/issues/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "bug", "limit": 10}'
```

### 2. Test Gemini Context Caching

#### Prerequisites
- Set `GEMINI_API_KEY` in your `.env` file
- Set `LLM_PROVIDER=gemini` in your `.env` file

#### Test Steps

1. **Test Gemini Client**:
   ```python
   from gemini_client import GeminiClient
   
   client = GeminiClient(use_context_caching=True)
   
   # Test implicit caching
   response = client.chat_with_implicit_caching(
       system_prompt="You are a helpful assistant",
       code_context={"code_block": "def test(): pass", "language": "python"},
       history_context=None,
       user_question="What does this code do?",
   )
   print(response)
   ```

2. **Test Context Caching**:
   ```python
   # Create cache
   block_ref = {"repo_name": "test", "path": "test.py", "start_line": 1}
   cache_key = client.create_context_cache(
       block_ref_dict=block_ref,
       system_prompt="Test prompt",
       code_context={"code_block": "def test(): pass"},
       history_context=None,
   )
   
   # Use cached context
   response = client.chat_with_cached_context(
       cache_key=cache_key,
       user_question="What are the potential issues?",
   )
   print(response)
   ```

#### Test via Agent

```python
from agent import GitHistoryAgent
from models import BlockRef

agent = GitHistoryAgent(
    provider="gemini",
    use_context_caching=True,
)

block_ref = BlockRef(
    repo_owner="test",
    repo_name="test-repo",
    ref="main",
    path="test.py",
    start_line=1,
    end_line=10,
)

# First question - creates cache
answer1 = agent.answer_question(
    block_ref=block_ref,
    question="What does this code do?",
)

# Second question - uses cache
answer2 = agent.answer_question(
    block_ref=block_ref,
    question="What are potential improvements?",
)
```

### 3. Test Agent with OpenAI

#### Prerequisites
- Set `OPENAI_API_KEY` in your `.env` file
- Set `LLM_PROVIDER=openai` (or leave default)
- Have a local git repository set up in `REPOS_ROOT`

#### Test Steps

1. **Setup Test Repository**:
   ```bash
   mkdir -p test_repos/test-repo
   cd test_repos/test-repo
   git init
   echo "def test(): pass" > test.py
   git add test.py
   git commit -m "Initial commit"
   ```

2. **Test Agent**:
   ```python
   from agent import GitHistoryAgent
   from models import BlockRef
   
   agent = GitHistoryAgent(provider="openai")
   
   block_ref = BlockRef(
       repo_owner="test",
       repo_name="test-repo",
       ref="main",
       path="test.py",
       start_line=1,
       end_line=5,
   )
   
   answer = agent.answer_question(
       block_ref=block_ref,
       question="What does this code do?",
   )
   print(answer)
   ```

#### Test via API

```bash
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "block_ref": {
      "repo_owner": "test",
      "repo_name": "test-repo",
      "ref": "main",
      "path": "test.py",
      "start_line": 1,
      "end_line": 5
    },
    "question": "What does this code do?"
  }'
```

### 4. Test API Endpoints

#### Start the Server

```bash
cd src
uvicorn llm_client:app --reload
```

#### Test Endpoints

1. **Health Check** (if implemented):
   ```bash
   curl http://127.0.0.1:8000/health
   ```

2. **Chat Endpoint**:
   ```bash
   curl -X POST "http://127.0.0.1:8000/chat" \
     -H "Content-Type: application/json" \
     -d @test_request.json
   ```

3. **Linear Endpoints**:
   ```bash
   # Get teams
   curl http://127.0.0.1:8000/linear/teams
   
   # Search issues
   curl -X POST "http://127.0.0.1:8000/linear/issues/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "test", "limit": 10}'
   ```

4. **Swagger UI**:
   Visit http://127.0.0.1:8000/docs to test endpoints interactively

## Test Scenarios

### Scenario 1: Linear Integration
- ✅ Create Linear issue from code analysis
- ✅ Search for existing issues
- ✅ Link code blocks to issues
- ✅ Handle API errors gracefully

### Scenario 2: Gemini Context Caching
- ✅ Cache creation and retrieval
- ✅ Cache expiration
- ✅ Implicit caching with common prefixes
- ✅ Cost savings verification

### Scenario 3: Multi-Provider Support
- ✅ OpenAI agent works
- ✅ Gemini agent works
- ✅ Provider switching
- ✅ Error handling for missing providers

### Scenario 4: API Endpoints
- ✅ Chat endpoint works
- ✅ Linear endpoints work
- ✅ CORS headers present
- ✅ Error handling

### Scenario 5: Git Operations
- ✅ Code context retrieval
- ✅ Git history retrieval
- ✅ Blame information
- ✅ Commit summaries

## Troubleshooting

### Common Issues

1. **Linear API Key Not Found**:
   - Set `LINEAR_API_KEY` in `.env` file
   - Check API key is valid
   - Verify API key has correct permissions

2. **Gemini API Key Not Found**:
   - Set `GEMINI_API_KEY` in `.env` file
   - Check API key is valid
   - Verify API key has access to Gemini API

3. **Repository Not Found**:
   - Set `REPOS_ROOT` in `.env` file
   - Ensure repository exists at specified path
   - Check repository name matches `repo_name` in BlockRef

4. **OpenAI API Errors**:
   - Check `OPENAI_API_KEY` is set
   - Verify API key is valid
   - Check API quota/limits

5. **Import Errors**:
   - Install all dependencies: `pip install -r requirements.txt`
   - Install test dependencies: `pip install -r requirements-test.txt`
   - Check Python path includes `src/` directory

### Debug Mode

Run tests with verbose output:
```bash
pytest -v
```

Run tests with print statements:
```bash
pytest -s
```

Run specific test with debugging:
```bash
pytest tests/test_agent.py::TestGitHistoryAgent::test_answer_question_openai -v -s
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-test.txt
      - run: pytest --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## Performance Testing

### Load Testing

```bash
# Install locust
pip install locust

# Run load tests
locust -f tests/load_test.py
```

### Benchmarking

```python
import time
from agent import GitHistoryAgent

agent = GitHistoryAgent()
start = time.time()
answer = agent.answer_question(block_ref, question)
end = time.time()
print(f"Response time: {end - start:.2f}s")
```

## Next Steps

1. **Add More Test Coverage**:
   - Edge cases
   - Error conditions
   - Boundary conditions
   - Integration scenarios

2. **Add E2E Tests**:
   - Full workflow tests
   - User journey tests
   - Performance tests

3. **Add Monitoring**:
   - Test execution metrics
   - Coverage reports
   - Performance benchmarks

4. **Add CI/CD**:
   - Automated testing
   - Code quality checks
   - Deployment automation

---

**Last Updated**: 2024
**Status**: Ready for Testing


