"""Conversation memory management for maintaining context across multiple questions."""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from models import BlockRef


@dataclass
class ConversationMessage:
    """A single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    block_ref: Optional[BlockRef] = None  # The code block this message relates to
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "block_ref": self.block_ref.model_dump() if self.block_ref else None,
        }


@dataclass
class ConversationSession:
    """A conversation session with history."""
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    messages: List[ConversationMessage] = field(default_factory=list)
    current_block_ref: Optional[BlockRef] = None  # Current code block being discussed
    
    def add_message(self, role: str, content: str, block_ref: Optional[BlockRef] = None):
        """Add a message to the conversation."""
        message = ConversationMessage(
            role=role,
            content=content,
            block_ref=block_ref or self.current_block_ref,
        )
        self.messages.append(message)
        self.last_accessed = time.time()
        if block_ref:
            self.current_block_ref = block_ref
    
    def get_recent_messages(self, max_messages: int = 10) -> List[ConversationMessage]:
        """Get the most recent messages, up to max_messages."""
        return self.messages[-max_messages:]
    
    def get_conversation_summary(self, max_length: int = 500) -> str:
        """Get a summary of the conversation for context."""
        if not self.messages:
            return ""
        
        summary_parts = []
        for msg in self.messages[-5:]:  # Last 5 messages
            role_label = "User" if msg.role == "user" else "Assistant"
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            summary_parts.append(f"{role_label}: {content_preview}")
        
        summary = "\n".join(summary_parts)
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "message_count": len(self.messages),
            "current_block_ref": self.current_block_ref.model_dump() if self.current_block_ref else None,
        }


class ConversationMemory:
    """Manages conversation memory across multiple sessions."""
    
    def __init__(self, ttl_seconds: int = 3600, max_sessions: int = 1000):
        """Initialize the conversation memory manager.
        
        Args:
            ttl_seconds: Time-to-live for sessions in seconds (default: 1 hour).
            max_sessions: Maximum number of sessions to keep in memory (default: 1000).
        """
        self.sessions: Dict[str, ConversationSession] = {}
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
    
    def create_session(self, initial_block_ref: Optional[BlockRef] = None) -> str:
        """Create a new conversation session.
        
        Args:
            initial_block_ref: Optional initial code block reference.
        
        Returns:
            str: Session ID.
        """
        session_id = str(uuid.uuid4())
        session = ConversationSession(
            session_id=session_id,
            current_block_ref=initial_block_ref,
        )
        self.sessions[session_id] = session
        
        # Clean up old sessions if we're at capacity
        if len(self.sessions) > self.max_sessions:
            self._cleanup_old_sessions()
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a conversation session by ID.
        
        Args:
            session_id: Session ID.
        
        Returns:
            Optional[ConversationSession]: Session if found and not expired, None otherwise.
        """
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # Check if session has expired
        if time.time() - session.last_accessed > self.ttl_seconds:
            del self.sessions[session_id]
            return None
        
        return session
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        block_ref: Optional[BlockRef] = None,
    ) -> bool:
        """Add a message to a conversation session.
        
        Args:
            session_id: Session ID.
            role: Message role ("user" or "assistant").
            content: Message content.
            block_ref: Optional code block reference.
        
        Returns:
            bool: True if message was added, False if session not found.
        """
        session = self.get_session(session_id)
        if not session:
            return False
        
        session.add_message(role, content, block_ref)
        return True
    
    def get_conversation_history(
        self,
        session_id: str,
        max_messages: int = 10,
        include_summary: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Get conversation history for a session.
        
        Args:
            session_id: Session ID.
            max_messages: Maximum number of recent messages to return.
            include_summary: Whether to include a conversation summary.
        
        Returns:
            Optional[Dict[str, Any]]: Conversation history or None if session not found.
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        messages = session.get_recent_messages(max_messages)
        history = {
            "session_id": session_id,
            "messages": [msg.to_dict() for msg in messages],
            "current_block_ref": session.current_block_ref.model_dump() if session.current_block_ref else None,
        }
        
        if include_summary:
            history["summary"] = session.get_conversation_summary()
        
        return history
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session.
        
        Args:
            session_id: Session ID.
        
        Returns:
            bool: True if session was deleted, False if not found.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def _cleanup_old_sessions(self):
        """Remove expired sessions and oldest sessions if over capacity."""
        current_time = time.time()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if current_time - session.last_accessed > self.ttl_seconds
        ]
        
        for sid in expired_sessions:
            del self.sessions[sid]
        
        # If still over capacity, remove oldest sessions
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.items(),
                key=lambda x: x[1].last_accessed,
            )
            sessions_to_remove = len(self.sessions) - self.max_sessions
            for sid, _ in sorted_sessions[:sessions_to_remove]:
                del self.sessions[sid]
    
    def cleanup_expired_sessions(self) -> int:
        """Remove all expired sessions.
        
        Returns:
            int: Number of sessions removed.
        """
        before_count = len(self.sessions)
        self._cleanup_old_sessions()
        return before_count - len(self.sessions)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about active sessions.
        
        Returns:
            Dict[str, Any]: Session statistics.
        """
        active_sessions = [
            s for s in self.sessions.values()
            if time.time() - s.last_accessed <= self.ttl_seconds
        ]
        
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "max_sessions": self.max_sessions,
            "ttl_seconds": self.ttl_seconds,
        }


# Global conversation memory instance
_conversation_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """Get or create the global conversation memory instance.
    
    Returns:
        ConversationMemory: Global conversation memory instance.
    """
    global _conversation_memory
    if _conversation_memory is None:
        _conversation_memory = ConversationMemory()
    return _conversation_memory


__all__ = [
    "ConversationMessage",
    "ConversationSession",
    "ConversationMemory",
    "get_conversation_memory",
]


