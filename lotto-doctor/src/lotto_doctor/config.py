"""Configuration loader for Lotto Doctor."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "default.yaml"


def _find_config_path() -> Path:
    """Find config/default.yaml relative to project root."""
    # Try several candidate locations
    candidates = [
        _CONFIG_PATH,
        Path("config/default.yaml"),
        Path(__file__).parent.parent.parent / "config" / "default.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "config/default.yaml not found. Run from the project root or install the package."
    )


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file and environment variables."""
    if config_path is None:
        config_path = _find_config_path()

    with open(config_path, "r", encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f)

    # Override DB path from env if set
    db_env = os.environ.get("LOTTO_DB_PATH")
    if db_env:
        cfg.setdefault("data", {})["db_path"] = db_env

    return cfg


def get_db_path(cfg: dict[str, Any] | None = None) -> Path:
    """Return resolved SQLite database path."""
    if cfg is None:
        cfg = load_config()
    raw = cfg.get("data", {}).get("db_path", "data/lotto.db")
    p = Path(raw)
    if not p.is_absolute():
        # Resolve relative to cwd (project root when running scripts)
        p = Path.cwd() / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_telegram_credentials() -> tuple[str, str]:
    """Return (bot_token, chat_id) from environment variables."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN environment variable is not set. "
            "Copy .env.example to .env and fill in your credentials."
        )
    if not chat_id:
        raise ValueError(
            "TELEGRAM_CHAT_ID environment variable is not set. "
            "Copy .env.example to .env and fill in your credentials."
        )
    return token, chat_id
