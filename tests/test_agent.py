"""Tests for GitHistoryAgent."""
import pytest
from unittest.mock import patch, Mock

from agent import GitHistoryAgent
from models import BlockRef


class TestGitHistoryAgent:
    """Tests for GitHistoryAgent."""
    
    def test_agent_init_openai(self, monkeypatch):
        """Test agent initialization with OpenAI."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch("openai.OpenAI"):
            agent = GitHistoryAgent(provider="openai")
            assert agent.provider == "openai"
            assert agent.client is not None
            assert agent.gemini_client is None
    
    def test_agent_init_gemini(self, monkeypatch):
        """Test agent initialization with Gemini."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        with patch("google.generativeai.configure"):
            agent = GitHistoryAgent(provider="gemini")
            assert agent.provider == "gemini"
            assert agent.gemini_client is not None
            assert agent.client is None
    
    def test_agent_init_gemini_not_available(self, monkeypatch):
        """Test agent initialization when Gemini is not available."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        with patch("agent.GEMINI_AVAILABLE", False):
            with pytest.raises(ImportError, match="Gemini client not available"):
                GitHistoryAgent(provider="gemini")
    
    def test_build_system_prompt(self, monkeypatch):
        """Test system prompt construction."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch("openai.OpenAI"):
            agent = GitHistoryAgent()
            prompt = agent.build_system_prompt()
            assert "code history assistant" in prompt.lower()
            assert "tools" in prompt.lower()
    
    def test_tool_definitions(self, monkeypatch):
        """Test tool definitions."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch("openai.OpenAI"):
            agent = GitHistoryAgent()
            tools = agent._tool_definitions()
            assert len(tools) > 0
            tool_names = [t["function"]["name"] for t in tools]
            assert "get_code_context" in tool_names
            assert "get_history_context" in tool_names
            assert "get_linear_issues_for_block" in tool_names
    
    @patch("agent.get_code_context_tool")
    @patch("agent.get_history_context_tool")
    def test_execute_tool_get_code_context(self, mock_history, mock_code, mock_block_ref, monkeypatch):
        """Test executing get_code_context tool."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        with patch("openai.OpenAI"):
            from models import CodeContext
            
            agent = GitHistoryAgent()
            mock_code.return_value = CodeContext(
                block_ref=mock_block_ref,
                code_block="def test(): pass",
                surrounding_code="def test(): pass",
                context_start_line=1,
                context_end_line=10,
                file_total_lines=10,
            )
            
            result = agent._execute_tool(
                "get_code_context",
                {"context_lines": 10},
                mock_block_ref,
            )
            
            assert "code_block" in result
            mock_code.assert_called_once()
    
    @patch("agent.OpenAI")
    def test_answer_question_openai(self, mock_openai_class, mock_block_ref, monkeypatch):
        """Test answering a question with OpenAI."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        
        # Mock OpenAI client and response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Test answer"
        mock_response.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value = mock_response
        
        agent = GitHistoryAgent(provider="openai")
        answer = agent.answer_question(
            block_ref=mock_block_ref,
            question="What does this code do?",
        )
        
        assert answer == "Test answer"
        mock_client.chat.completions.create.assert_called()


