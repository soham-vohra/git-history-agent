from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """
    Central configuration object for the Andromeda backend.

    All environment-dependent configuration values are loaded here.
    Any module needing configuration should import from `settings`
    instead of accessing os.getenv directly.
    """
    openai_api_key: str
    repo_base_dir: Path

    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "Settings":
        # --- OpenAI API key (required) ---
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Please add it to your .env file or environment."
            )

        # --- Repo base directory (required-ish) ---
        repo_base_dir_str = (
            os.getenv("REPO_BASE_DIR")
            or os.getenv("REPOS_ROOT")
            or "./data/repos"
        )
        repo_base_dir = Path(repo_base_dir_str).expanduser().resolve()
        repo_base_dir.mkdir(parents=True, exist_ok=True)

        # --- Supabase (optional for now) ---
        supabase_url = os.getenv("SUPABASE_URL") or None
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY") or None

        return cls(
            openai_api_key=openai_api_key,
            repo_base_dir=repo_base_dir,
            supabase_url=supabase_url,
            supabase_anon_key=supabase_anon_key,
        )


# Global settings instance
settings = Settings.from_env()
