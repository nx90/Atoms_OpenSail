"""Verify migration 0123 adds per-user agent overrides."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def test_0123_upgrade_adds_agent_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "system-default-overrides.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    monkeypatch.setenv("DEPLOYMENT_MODE", "desktop")
    from app.config import get_settings

    get_settings.cache_clear()
    orchestrator_dir = Path(__file__).resolve().parents[2]
    config = Config(str(orchestrator_dir / "alembic.ini"))
    config.set_main_option("script_location", str(orchestrator_dir / "alembic"))
    original_cwd = os.getcwd()
    os.chdir(orchestrator_dir)
    try:
        command.upgrade(config, "head")
    finally:
        os.chdir(original_cwd)
        get_settings.cache_clear()

    connection = sqlite3.connect(database)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info('user_purchased_agents')")
        }
        assert "agent_overrides" in columns
    finally:
        connection.close()