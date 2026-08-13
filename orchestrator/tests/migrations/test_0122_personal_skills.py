"""Verify migration 0122 creates the personal skill workspace schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture
def sqlite_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = tmp_path / "personal-skills.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("DEPLOYMENT_MODE", "desktop")
    from app.config import get_settings

    get_settings.cache_clear()
    yield str(db_path)
    get_settings.cache_clear()


def _alembic_cfg() -> Config:
    orchestrator_dir = Path(__file__).resolve().parents[2]
    config = Config(str(orchestrator_dir / "alembic.ini"))
    config.set_main_option("script_location", str(orchestrator_dir / "alembic"))
    return config


def test_0122_upgrade_creates_personal_skill_tables(sqlite_db: str) -> None:
    original_cwd = os.getcwd()
    orchestrator_dir = Path(__file__).resolve().parents[2]
    os.chdir(orchestrator_dir)
    try:
        command.upgrade(_alembic_cfg(), "head")
    finally:
        os.chdir(original_cwd)

    connection = sqlite3.connect(sqlite_db)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {
            "personal_skills",
            "personal_skill_files",
            "personal_skill_assignments",
        } <= tables

        skill_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('personal_skills')")
        }
        assert {"user_id", "normalized_name", "description", "revision"} <= skill_columns

        file_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('personal_skill_files')")
        }
        assert {"skill_id", "path", "is_directory", "content", "size_bytes"} <= file_columns
    finally:
        connection.close()
