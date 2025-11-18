"""Tests for Gemini client."""
import pytest
from unittest.mock import patch, Mock
from datetime import datetime, timedelta

from gemini_client import GeminiClient, GeminiError, ContextCache


class TestContextCache:
    """Tests for ContextCache."""
    
    def test_cache_creation(self):
        """Test creating a cache."""
        cache = ContextCache(ttl_seconds=3600)
        cache_key = cache.create_cache("key1", "test content", "Test Cache")
        
        assert cache_key == "key1"
        assert cache.get_cache("key1") == "test content"
    
    def test_cache_expiration(self):
        """Test cache expiration."""
        cache = ContextCache(ttl_seconds=1)  # 1 second TTL
        cache.create_cache("key1", "test content")
        
        # Should be available immediately
        assert cache.get_cache("key1") == "test content"
        
        # Wait for expiration (in real test, you'd use time.sleep or mock time)
        # For now, we'll test the cleanup method
        cache._cache_metadata["key1"] = datetime.now() - timedelta(seconds=2)
        expired_count = cache.cleanup_expired()
        assert expired_count == 1
        assert cache.get_cache("key1") is None
    
    def test_cache_key_generation(self):
        """Test cache key generation."""
        cache = ContextCache()
        block_ref = {
            "repo_owner": "test",
            "repo_name": "test-repo",
            "path": "test.py",
            "start_line": 1,
            "end_line": 10,
        }
        key1 = cache._generate_cache_key(block_ref, "code")
        key2 = cache._generate_cache_key(block_ref, "code")
        
        # Same input should generate same key
        assert key1 == key2
        
        # Different context type should generate different key
        key3 = cache._generate_cache_key(block_ref, "history")
        assert key1 != key3
    
    def test_delete_cache(self):
        """Test deleting a cache."""
        cache = ContextCache()
        cache.create_cache("key1", "content")
        
        assert cache.delete_cache("key1") is True
        assert cache.get_cache("key1") is None
        assert cache.delete_cache("key1") is False  # Already deleted


class TestGeminiClient:
    """Tests for GeminiClient."""
    
    def test_gemini_client_init_without_key(self, monkeypatch):
        """Test GeminiClient initialization without API key."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(GeminiError, match="Gemini API key not found"):
            GeminiClient()
    
    @patch("google.generativeai.configure")
    def test_gemini_client_init_with_key(self, mock_configure, monkeypatch):
        """Test GeminiClient initialization with API key."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        client = GeminiClient()
        assert client.api_key == "test-key"
        mock_configure.assert_called_once()
    
    @patch("google.generativeai.GenerativeModel")
    def test_chat_with_implicit_caching(self, mock_model, monkeypatch):
        """Test chat with implicit caching."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        client = GeminiClient()
        
        # Mock model and response
        mock_instance = Mock()
        mock_model.return_value = mock_instance
        mock_response = Mock()
        mock_response.text = "Test response"
        mock_instance.generate_content.return_value = mock_response
        
        # Test chat
        response = client.chat_with_implicit_caching(
            system_prompt="You are a helpful assistant",
            code_context={"code_block": "def test(): pass", "language": "python"},
            history_context=None,
            user_question="What does this code do?",
        )
        
        assert response == "Test response"
        mock_instance.generate_content.assert_called_once()
    
    def test_create_context_cache(self, monkeypatch):
        """Test creating a context cache."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        with patch("google.generativeai.configure"):
            client = GeminiClient(use_context_caching=True)
            
            block_ref = {
                "repo_name": "test-repo",
                "path": "test.py",
                "start_line": 1,
            }
            
            cache_key = client.create_context_cache(
                block_ref_dict=block_ref,
                system_prompt="Test prompt",
                code_context={"code_block": "def test(): pass"},
                history_context=None,
            )
            
            assert cache_key is not None
            # Verify cache was created
            cached_content = client.context_cache.get_cache(cache_key)
            assert cached_content is not None
            assert "Test prompt" in cached_content
            assert "def test(): pass" in cached_content


