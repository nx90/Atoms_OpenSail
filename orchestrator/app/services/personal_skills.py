"""Persistence and validation for private user-authored skill folders."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

import yaml
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import PersonalSkill, PersonalSkillAssignment, PersonalSkillFile

ROOT_SKILL_FILE = "SKILL.md"


class PersonalSkillError(Exception):
    """Base domain error for personal skill operations."""


class PersonalSkillNotFoundError(PersonalSkillError):
    pass


class PersonalSkillValidationError(PersonalSkillError):
    pass


class PersonalSkillConflictError(PersonalSkillError):
    pass


class PersonalSkillLimitError(PersonalSkillError):
    pass


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str


def normalize_skill_name(name: str) -> str:
    normalized = " ".join(name.strip().split()).casefold()
    if not normalized:
        raise PersonalSkillValidationError("Skill name is required")
    return normalized


def normalize_skill_path(path: str) -> str:
    settings = get_settings()
    value = path.replace("\\", "/").strip()
    if not value or "\x00" in value or value.startswith("/"):
        raise PersonalSkillValidationError("Path must be a non-empty relative path")
    if "//" in value:
        raise PersonalSkillValidationError("Path cannot contain repeated separators")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PersonalSkillValidationError("Path cannot contain empty, '.' or '..' segments")
    if len(value) > settings.personal_skill_max_path_length:
        raise PersonalSkillLimitError("Path exceeds the configured maximum length")
    if len(parts) > settings.personal_skill_max_depth:
        raise PersonalSkillLimitError("Path exceeds the configured nesting depth")
    canonical = str(PurePosixPath(*parts))
    if canonical != value:
        raise PersonalSkillValidationError("Path is not canonical")
    return canonical


def parse_skill_metadata(content: str) -> SkillMetadata:
    if not content.startswith("---"):
        raise PersonalSkillValidationError("SKILL.md must start with YAML frontmatter")
    end = content.find("---", 3)
    if end == -1:
        raise PersonalSkillValidationError("SKILL.md frontmatter is not closed")
    try:
        frontmatter = yaml.safe_load(content[3:end].strip())
    except yaml.YAMLError as exc:
        raise PersonalSkillValidationError(f"Invalid SKILL.md frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise PersonalSkillValidationError("SKILL.md frontmatter must be a mapping")
    name = str(frontmatter.get("name") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    if not name:
        raise PersonalSkillValidationError("SKILL.md frontmatter requires a name")
    if len(name) > 100:
        raise PersonalSkillValidationError("Skill name cannot exceed 100 characters")
    return SkillMetadata(name=name, description=description)


def strip_skill_frontmatter(content: str) -> str:
    """Return the instruction body after validating root YAML frontmatter."""
    parse_skill_metadata(content)
    end = content.find("---", 3)
    return content[end + 3 :].strip()


def render_default_skill(name: str, description: str) -> str:
    frontmatter = yaml.safe_dump(
        {"name": name.strip(), "description": description.strip()},
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return f"---\n{frontmatter}\n---\n\n# {name.strip()}\n\nAdd skill instructions here.\n"


class PersonalSkillService:
    def __init__(self, db: AsyncSession, user_id: UUID) -> None:
        self.db = db
        self.user_id = user_id
        self.settings = get_settings()

    async def get_owned(self, skill_id: UUID, *, lock: bool = False) -> PersonalSkill:
        query = select(PersonalSkill).where(
            PersonalSkill.id == skill_id,
            PersonalSkill.user_id == self.user_id,
        )
        if lock:
            query = query.with_for_update()
        skill = (await self.db.execute(query)).scalar_one_or_none()
        if skill is None:
            raise PersonalSkillNotFoundError("Personal skill not found")
        return skill

    async def list_skills(self) -> list[PersonalSkill]:
        result = await self.db.execute(
            select(PersonalSkill)
            .where(PersonalSkill.user_id == self.user_id)
            .order_by(PersonalSkill.updated_at.desc(), PersonalSkill.name.asc())
        )
        return list(result.scalars().all())

    async def create_skill(self, name: str, description: str = "") -> PersonalSkill:
        count = await self.db.scalar(
            select(func.count(PersonalSkill.id)).where(PersonalSkill.user_id == self.user_id)
        )
        if int(count or 0) >= self.settings.personal_skills_max_per_user:
            raise PersonalSkillLimitError("Personal skill limit reached")
        name = name.strip()
        if not name or len(name) > 100:
            raise PersonalSkillValidationError("Skill name must be between 1 and 100 characters")
        content = render_default_skill(name, description)
        encoded = content.encode("utf-8")
        skill = PersonalSkill(
            user_id=self.user_id,
            name=name,
            normalized_name=normalize_skill_name(name),
            description=description.strip(),
        )
        skill.files.append(
            PersonalSkillFile(
                path=ROOT_SKILL_FILE,
                is_directory=False,
                content=content,
                size_bytes=len(encoded),
            )
        )
        self.db.add(skill)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PersonalSkillConflictError("A personal skill with this name already exists") from exc
        await self.db.refresh(skill)
        return skill

    async def delete_skill(self, skill_id: UUID) -> None:
        skill = await self.get_owned(skill_id)
        await self.db.delete(skill)
        await self.db.commit()

    async def list_entries(self, skill_id: UUID) -> tuple[PersonalSkill, list[PersonalSkillFile]]:
        skill = await self.get_owned(skill_id)
        result = await self.db.execute(
            select(PersonalSkillFile)
            .where(PersonalSkillFile.skill_id == skill.id)
            .order_by(PersonalSkillFile.path.asc())
        )
        return skill, list(result.scalars().all())

    async def read_file(self, skill_id: UUID, path: str) -> tuple[PersonalSkill, PersonalSkillFile]:
        skill = await self.get_owned(skill_id)
        canonical = normalize_skill_path(path)
        entry = (
            await self.db.execute(
                select(PersonalSkillFile).where(
                    PersonalSkillFile.skill_id == skill.id,
                    PersonalSkillFile.path == canonical,
                    PersonalSkillFile.is_directory.is_(False),
                )
            )
        ).scalar_one_or_none()
        if entry is None:
            raise PersonalSkillNotFoundError("Skill file not found")
        return skill, entry

    async def put_file(
        self, skill_id: UUID, path: str, content: str, expected_revision: int
    ) -> tuple[PersonalSkill, PersonalSkillFile]:
        canonical = normalize_skill_path(path)
        self._validate_text(content)
        skill = await self.get_owned(skill_id, lock=True)
        self._check_revision(skill, expected_revision)
        await self._ensure_parent_directories(skill, canonical)
        entry = (
            await self.db.execute(
                select(PersonalSkillFile).where(
                    PersonalSkillFile.skill_id == skill.id,
                    PersonalSkillFile.path == canonical,
                )
            )
        ).scalar_one_or_none()
        if entry is not None and entry.is_directory:
            raise PersonalSkillConflictError("A directory already exists at this path")
        encoded_size = len(content.encode("utf-8"))
        await self._check_capacity(skill, canonical, encoded_size, entry)
        if entry is None:
            entry = PersonalSkillFile(
                skill_id=skill.id,
                path=canonical,
                is_directory=False,
                content=content,
                size_bytes=encoded_size,
            )
            self.db.add(entry)
        else:
            entry.content = content
            entry.size_bytes = encoded_size
        if canonical == ROOT_SKILL_FILE:
            metadata = parse_skill_metadata(content)
            skill.name = metadata.name
            skill.normalized_name = normalize_skill_name(metadata.name)
            skill.description = metadata.description
        skill.revision += 1
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PersonalSkillConflictError("A skill or file with this name already exists") from exc
        await self.db.refresh(skill)
        await self.db.refresh(entry)
        return skill, entry

    async def create_directory(
        self, skill_id: UUID, path: str, expected_revision: int
    ) -> PersonalSkill:
        canonical = normalize_skill_path(path)
        if canonical == ROOT_SKILL_FILE:
            raise PersonalSkillConflictError("SKILL.md is a file")
        skill = await self.get_owned(skill_id, lock=True)
        self._check_revision(skill, expected_revision)
        await self._ensure_parent_directories(skill, canonical)
        existing = await self.db.scalar(
            select(PersonalSkillFile.id).where(
                PersonalSkillFile.skill_id == skill.id,
                PersonalSkillFile.path == canonical,
            )
        )
        if existing is not None:
            raise PersonalSkillConflictError("An entry already exists at this path")
        await self._check_entry_count(skill, 1)
        self.db.add(
            PersonalSkillFile(
                skill_id=skill.id,
                path=canonical,
                is_directory=True,
                content=None,
                size_bytes=0,
            )
        )
        skill.revision += 1
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def rename_entry(
        self, skill_id: UUID, old_path: str, new_path: str, expected_revision: int
    ) -> PersonalSkill:
        old = normalize_skill_path(old_path)
        new = normalize_skill_path(new_path)
        if old == ROOT_SKILL_FILE or new == ROOT_SKILL_FILE:
            raise PersonalSkillValidationError("Root SKILL.md cannot be renamed")
        if new.startswith(f"{old}/"):
            raise PersonalSkillValidationError("An entry cannot be moved inside itself")
        skill = await self.get_owned(skill_id, lock=True)
        self._check_revision(skill, expected_revision)
        entries = list(
            (
                await self.db.execute(
                    select(PersonalSkillFile).where(
                        PersonalSkillFile.skill_id == skill.id,
                        (PersonalSkillFile.path == old)
                        | PersonalSkillFile.path.startswith(f"{old}/"),
                    )
                )
            ).scalars().all()
        )
        if not entries:
            raise PersonalSkillNotFoundError("Skill entry not found")
        await self._ensure_parent_directories(skill, new)
        replacements = {
            entry.path: new + entry.path[len(old) :]
            for entry in entries
        }
        conflicts = set(
            (
                await self.db.scalars(
            select(PersonalSkillFile.path).where(
                PersonalSkillFile.skill_id == skill.id,
                PersonalSkillFile.path.in_(list(replacements.values())),
            )
                )
            ).all()
        )
        if conflicts - set(replacements):
            raise PersonalSkillConflictError("An entry already exists at the destination")
        for entry in entries:
            entry.path = replacements[entry.path]
        skill.revision += 1
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def delete_entry(
        self, skill_id: UUID, path: str, expected_revision: int
    ) -> PersonalSkill:
        canonical = normalize_skill_path(path)
        if canonical == ROOT_SKILL_FILE:
            raise PersonalSkillValidationError("Root SKILL.md cannot be deleted")
        skill = await self.get_owned(skill_id, lock=True)
        self._check_revision(skill, expected_revision)
        result = await self.db.execute(
            delete(PersonalSkillFile).where(
                PersonalSkillFile.skill_id == skill.id,
                (PersonalSkillFile.path == canonical)
                | PersonalSkillFile.path.startswith(f"{canonical}/"),
            )
        )
        if not result.rowcount:
            raise PersonalSkillNotFoundError("Skill entry not found")
        skill.revision += 1
        await self.db.commit()
        await self.db.refresh(skill)
        return skill

    async def bind(self, skill_id: UUID, agent_id: UUID) -> PersonalSkillAssignment:
        skill = await self.get_owned(skill_id)
        existing = (
            await self.db.execute(
                select(PersonalSkillAssignment).where(
                    PersonalSkillAssignment.skill_id == skill.id,
                    PersonalSkillAssignment.agent_id == agent_id,
                    PersonalSkillAssignment.user_id == self.user_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.enabled = True
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        assignment = PersonalSkillAssignment(
            skill_id=skill.id,
            agent_id=agent_id,
            user_id=self.user_id,
            enabled=True,
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def unbind(self, skill_id: UUID, agent_id: UUID) -> None:
        await self.get_owned(skill_id)
        result = await self.db.execute(
            delete(PersonalSkillAssignment).where(
                PersonalSkillAssignment.skill_id == skill_id,
                PersonalSkillAssignment.agent_id == agent_id,
                PersonalSkillAssignment.user_id == self.user_id,
            )
        )
        if not result.rowcount:
            raise PersonalSkillNotFoundError("Skill assignment not found")
        await self.db.commit()

    async def list_assignments(self, skill_id: UUID) -> list[PersonalSkillAssignment]:
        skill = await self.get_owned(skill_id)
        result = await self.db.execute(
            select(PersonalSkillAssignment).where(
                PersonalSkillAssignment.skill_id == skill.id,
                PersonalSkillAssignment.user_id == self.user_id,
                PersonalSkillAssignment.enabled.is_(True),
            )
        )
        return list(result.scalars().all())

    def _validate_text(self, content: str) -> None:
        if "\x00" in content:
            raise PersonalSkillValidationError("Text files cannot contain NUL bytes")
        size = len(content.encode("utf-8"))
        if size > self.settings.personal_skill_max_file_bytes:
            raise PersonalSkillLimitError("File exceeds the configured size limit")

    def _check_revision(self, skill: PersonalSkill, expected: int) -> None:
        if skill.revision != expected:
            raise PersonalSkillConflictError(
                f"Skill changed since it was opened (current revision: {skill.revision})"
            )

    async def _check_entry_count(self, skill: PersonalSkill, additional: int) -> None:
        count = await self.db.scalar(
            select(func.count(PersonalSkillFile.id)).where(PersonalSkillFile.skill_id == skill.id)
        )
        if int(count or 0) + additional > self.settings.personal_skill_max_entries:
            raise PersonalSkillLimitError("Skill entry limit reached")

    async def _check_capacity(
        self,
        skill: PersonalSkill,
        path: str,
        new_size: int,
        existing: PersonalSkillFile | None,
    ) -> None:
        if existing is None:
            await self._check_entry_count(skill, 1)
        total = await self.db.scalar(
            select(func.coalesce(func.sum(PersonalSkillFile.size_bytes), 0)).where(
                PersonalSkillFile.skill_id == skill.id
            )
        )
        old_size = existing.size_bytes if existing else 0
        if int(total or 0) - old_size + new_size > self.settings.personal_skill_max_total_bytes:
            raise PersonalSkillLimitError("Skill exceeds the configured total size limit")

    async def _ensure_parent_directories(self, skill: PersonalSkill, path: str) -> None:
        parts = path.split("/")[:-1]
        if not parts:
            return
        current: list[str] = []
        added = 0
        for part in parts:
            current.append(part)
            directory = "/".join(current)
            entry = (
                await self.db.execute(
                    select(PersonalSkillFile).where(
                        PersonalSkillFile.skill_id == skill.id,
                        PersonalSkillFile.path == directory,
                    )
                )
            ).scalar_one_or_none()
            if entry is not None:
                if not entry.is_directory:
                    raise PersonalSkillConflictError(
                        f"A file blocks the parent directory '{directory}'"
                    )
                continue
            self.db.add(
                PersonalSkillFile(
                    skill_id=skill.id,
                    path=directory,
                    is_directory=True,
                    content=None,
                    size_bytes=0,
                )
            )
            added += 1
        if added:
            await self._check_entry_count(skill, added)
