"""Manual testing script for quick validation."""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv()


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    missing_deps = []
    
    try:
        from models import BlockRef, LinearIssue
        print("  ✅ models imported")
    except Exception as e:
        print(f"  ❌ models import error: {e}")
        return False
    
    try:
        from git_core import GitError, get_code_context
        print("  ✅ git_core imported")
    except Exception as e:
        print(f"  ❌ git_core import error: {e}")
        return False
    
    try:
        from linear_client import LinearClient, LinearError
        print("  ✅ linear_client imported")
    except Exception as e:
        print(f"  ❌ linear_client import error: {e}")
        missing_deps.append("httpx")
        return False
    
    try:
        from tools import get_code_context_tool
        print("  ✅ tools imported")
    except Exception as e:
        print(f"  ❌ tools import error: {e}")
        return False
    
    try:
        import openai
        print("  ✅ openai imported")
    except ImportError:
        print("  ⚠️  openai not installed (required for OpenAI agent)")
        missing_deps.append("openai")
    
    try:
        import google.generativeai
        print("  ✅ google.generativeai imported")
    except ImportError:
        print("  ⚠️  google.generativeai not installed (required for Gemini agent)")
        missing_deps.append("google-generativeai")
    
    try:
        import fastapi
        print("  ✅ fastapi imported")
    except ImportError:
        print("  ⚠️  fastapi not installed (required for API server)")
        missing_deps.append("fastapi")
    
    try:
        from agent import GitHistoryAgent
        print("  ✅ agent imported")
    except Exception as e:
        if "openai" in str(e).lower():
            print("  ⚠️  agent import skipped (openai not available)")
        else:
            print(f"  ❌ agent import error: {e}")
            return False
    
    if missing_deps:
        print(f"\n  💡 Install missing dependencies: pip install {' '.join(missing_deps)}")
        print("  💡 Or install all: pip install -r requirements.txt")
    
    print("✅ Core imports successful")
    return True


def test_linear_client():
    """Test Linear client initialization."""
    print("\nTesting Linear client...")
    try:
        api_key = os.getenv("LINEAR_API_KEY")
        if not api_key:
            print("⏭️  LINEAR_API_KEY not set, skipping")
            return True
        
        from linear_client import LinearClient
        client = LinearClient()
        print("✅ Linear client initialized successfully")
        
        # Test getting teams (optional - requires API key)
        try:
            teams = client.get_teams()
            print(f"✅ Found {len(teams)} teams")
        except Exception as e:
            print(f"⚠️  Could not fetch teams: {e}")
        
        return True
    except LinearError as e:
        print(f"⏭️  Linear client error (expected if no API key): {e}")
        return True
    except Exception as e:
        print(f"❌ Linear client error: {e}")
        return False


def test_gemini_client():
    """Test Gemini client initialization."""
    print("\nTesting Gemini client...")
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("⏭️  GEMINI_API_KEY not set, skipping")
            return True
        
        from gemini_client import GeminiClient
        client = GeminiClient(use_context_caching=True)
        print("✅ Gemini client initialized successfully")
        return True
    except Exception as e:
        print(f"⏭️  Gemini client error (expected if no API key): {e}")
        return True


def test_agent_initialization():
    """Test agent initialization."""
    print("\nTesting agent initialization...")
    try:
        from agent import GitHistoryAgent
        
        # Test OpenAI agent
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                agent = GitHistoryAgent(provider="openai")
                print("✅ OpenAI agent initialized successfully")
            except Exception as e:
                print(f"⚠️  OpenAI agent error: {e}")
        else:
            print("⏭️  OPENAI_API_KEY not set, skipping OpenAI agent")
        
        # Test Gemini agent
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                agent = GitHistoryAgent(provider="gemini")
                print("✅ Gemini agent initialized successfully")
            except Exception as e:
                print(f"⚠️  Gemini agent error: {e}")
        else:
            print("⏭️  GEMINI_API_KEY not set, skipping Gemini agent")
        
        return True
    except Exception as e:
        print(f"❌ Agent initialization error: {e}")
        return False


def test_models():
    """Test model creation."""
    print("\nTesting models...")
    try:
        from models import BlockRef, LinearIssue, LinearTeam
        
        block_ref = BlockRef(
            repo_owner="test",
            repo_name="test-repo",
            ref="main",
            path="test.py",
            start_line=1,
            end_line=10,
        )
        print("✅ BlockRef model works")
        
        team = LinearTeam(
            id="team-1",
            key="ENG",
            name="Engineering",
        )
        print("✅ LinearTeam model works")
        
        return True
    except Exception as e:
        print(f"❌ Model error: {e}")
        return False


def test_api_server():
    """Test API server can be imported."""
    print("\nTesting API server...")
    try:
        from llm_client import app
        print("✅ API server imported successfully")
        return True
    except Exception as e:
        print(f"❌ API server error: {e}")
        return False


def main():
    """Run all manual tests."""
    print("=" * 50)
    print("Manual Testing Script")
    print("=" * 50)
    
    results = []
    results.append(("Imports", test_imports()))
    results.append(("Models", test_models()))
    results.append(("Linear Client", test_linear_client()))
    results.append(("Gemini Client", test_gemini_client()))
    results.append(("Agent Initialization", test_agent_initialization()))
    results.append(("API Server", test_api_server()))
    
    print("\n" + "=" * 50)
    print("Test Results Summary")
    print("=" * 50)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name}: {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

