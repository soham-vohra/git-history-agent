# Quick Testing Guide

This guide helps you quickly test that everything works after setup.

## Step 1: Install Dependencies

```bash
# Install main dependencies
pip install -r requirements.txt

# Install test dependencies
pip install -r requirements-test.txt
```

## Step 2: Run Quick Test

```bash
python test_manual.py
```

This will test:
- ✅ All imports work
- ✅ Models can be created
- ✅ Clients can be initialized (if API keys are set)
- ✅ Agent can be initialized
- ✅ API server can be imported

## Step 3: Set Up Environment Variables

Create a `.env` file:

```bash
# Required for OpenAI agent
OPENAI_API_KEY=your-openai-api-key

# Required for Gemini agent
GEMINI_API_KEY=your-gemini-api-key

# Required for Linear integration
LINEAR_API_KEY=your-linear-api-key

# Optional: Repository root
REPOS_ROOT=./test_repos

# Optional: LLM provider (default: openai)
LLM_PROVIDER=openai
```

## Step 4: Run Unit Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_models.py -v
```

## Step 5: Test API Server

### Start the Server

```bash
cd src
uvicorn llm_client:app --reload
```

### Test Endpoints

1. **Visit Swagger UI**: http://127.0.0.1:8000/docs

2. **Test Chat Endpoint**:
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
         "end_line": 10
       },
       "question": "What does this code do?"
     }'
   ```

3. **Test Linear Endpoints** (if LINEAR_API_KEY is set):
   ```bash
   # Get teams
   curl http://127.0.0.1:8000/linear/teams
   
   # Search issues
   curl -X POST "http://127.0.0.1:8000/linear/issues/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "test", "limit": 10}'
   ```

## Step 6: Test with Real Repository

### Create Test Repository

```bash
mkdir -p test_repos/test-repo
cd test_repos/test-repo
git init
echo "def hello(): print('Hello, World!')" > hello.py
git add hello.py
git config user.name "Test User"
git config user.email "test@example.com"
git commit -m "Initial commit"
```

### Test Agent

```python
from agent import GitHistoryAgent
from models import BlockRef

agent = GitHistoryAgent(provider="openai")

block_ref = BlockRef(
    repo_owner="test",
    repo_name="test-repo",
    ref="main",
    path="hello.py",
    start_line=1,
    end_line=5,
)

answer = agent.answer_question(
    block_ref=block_ref,
    question="What does this code do?",
)
print(answer)
```

## Common Issues

### Issue: Module not found

**Solution**: Install dependencies
```bash
pip install -r requirements.txt
```

### Issue: API key not found

**Solution**: Set environment variables in `.env` file
```bash
OPENAI_API_KEY=your-key
GEMINI_API_KEY=your-key
LINEAR_API_KEY=your-key
```

### Issue: Repository not found

**Solution**: Set `REPOS_ROOT` in `.env` file
```bash
REPOS_ROOT=./test_repos
```

### Issue: Import errors in tests

**Solution**: Make sure `src/` is in Python path
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
```

Or install in development mode:
```bash
pip install -e .
```

## Next Steps

1. ✅ Verify all tests pass
2. ✅ Test API endpoints
3. ✅ Test with real repository
4. ✅ Test Linear integration (if API key is set)
5. ✅ Test Gemini integration (if API key is set)

## Need Help?

- Check [TESTING.md](TESTING.md) for detailed testing instructions
- Check [README.md](README.md) for setup instructions
- Check logs for error messages
- Verify API keys are correct
- Verify repository paths are correct

---

**Happy Testing!** 🚀


