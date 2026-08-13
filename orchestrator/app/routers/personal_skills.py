"""Private user-authored skill workspace API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import MarketplaceAgent, PersonalSkill, PersonalSkillFile, User
from ..services.default_agent import SYSTEM_DEFAULT_AGENT_ID
from ..services.marketplace_agent_scope import AgentScopeError, resolve_agent_in_user_scope
from ..services.personal_skills import (
    PersonalSkillConflictError,
    PersonalSkillError,
    PersonalSkillLimitError,
    PersonalSkillNotFoundError,
    PersonalSkillService,
    PersonalSkillValidationError,
)
from ..users import current_active_user

router = APIRouter(prefix="/api/personal-skills", tags=["personal-skills"])


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)


class SkillSummary(BaseModel):
    id: UUID
    name: str
    description: str
    revision: int
    created_at: datetime | None
    updated_at: datetime | None
    source: str = "personal"


class SkillEntry(BaseModel):
    path: str
    is_directory: bool
    size_bytes: int
    updated_at: datetime | None


class SkillTreeResponse(BaseModel):
    skill: SkillSummary
    entries: list[SkillEntry]


class SkillFileResponse(BaseModel):
    skill: SkillSummary
    path: str
    content: str
    size_bytes: int


class SkillFileWrite(BaseModel):
    path: str
    content: str
    expected_revision: int = Field(ge=1)


class SkillDirectoryCreate(BaseModel):
    path: str
    expected_revision: int = Field(ge=1)


class SkillRename(BaseModel):
    old_path: str
    new_path: str
    expected_revision: int = Field(ge=1)


class SkillAssignmentCreate(BaseModel):
    agent_id: UUID


def _summary(skill: PersonalSkill) -> SkillSummary:
    return SkillSummary(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        revision=skill.revision,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


def _entry(entry: PersonalSkillFile) -> SkillEntry:
    return SkillEntry(
        path=entry.path,
        is_directory=entry.is_directory,
        size_bytes=entry.size_bytes,
        updated_at=entry.updated_at,
    )


def _http_error(exc: PersonalSkillError) -> HTTPException:
    if isinstance(exc, PersonalSkillNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PersonalSkillConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PersonalSkillLimitError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, PersonalSkillValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


async def _resolve_bindable_agent(db: AsyncSession, agent_id: UUID, user: User) -> MarketplaceAgent:
    if agent_id == SYSTEM_DEFAULT_AGENT_ID:
        agent = await db.scalar(
            select(MarketplaceAgent).where(
                MarketplaceAgent.id == agent_id,
                MarketplaceAgent.is_active.is_(True),
                MarketplaceAgent.item_type == "agent",
            )
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="System Default Agent not found")
        return agent
    try:
        return await resolve_agent_in_user_scope(db, agent_id=agent_id, user=user)
    except AgentScopeError as exc:
        code = 404 if exc.reason == AgentScopeError.REASON_NOT_FOUND else 403
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.get("", response_model=list[SkillSummary])
async def list_personal_skills(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    return [_summary(skill) for skill in await PersonalSkillService(db, current_user.id).list_skills()]


@router.post("", response_model=SkillSummary, status_code=status.HTTP_201_CREATED)
async def create_personal_skill(
    body: SkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        skill = await PersonalSkillService(db, current_user.id).create_skill(
            body.name, body.description
        )
        return _summary(skill)
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}", response_model=SkillSummary)
async def get_personal_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        return _summary(await PersonalSkillService(db, current_user.id).get_owned(skill_id))
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        await PersonalSkillService(db, current_user.id).delete_skill(skill_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}/tree", response_model=SkillTreeResponse)
async def get_personal_skill_tree(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        skill, entries = await PersonalSkillService(db, current_user.id).list_entries(skill_id)
        return SkillTreeResponse(skill=_summary(skill), entries=[_entry(item) for item in entries])
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}/file", response_model=SkillFileResponse)
async def read_personal_skill_file(
    skill_id: UUID,
    path: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        skill, entry = await PersonalSkillService(db, current_user.id).read_file(skill_id, path)
        return SkillFileResponse(
            skill=_summary(skill),
            path=entry.path,
            content=entry.content or "",
            size_bytes=entry.size_bytes,
        )
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.put("/{skill_id}/file", response_model=SkillFileResponse)
async def write_personal_skill_file(
    skill_id: UUID,
    body: SkillFileWrite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        skill, entry = await PersonalSkillService(db, current_user.id).put_file(
            skill_id, body.path, body.content, body.expected_revision
        )
        return SkillFileResponse(
            skill=_summary(skill),
            path=entry.path,
            content=entry.content or "",
            size_bytes=entry.size_bytes,
        )
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/directory", response_model=SkillSummary)
async def create_personal_skill_directory(
    skill_id: UUID,
    body: SkillDirectoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        return _summary(
            await PersonalSkillService(db, current_user.id).create_directory(
                skill_id, body.path, body.expected_revision
            )
        )
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/rename", response_model=SkillSummary)
async def rename_personal_skill_entry(
    skill_id: UUID,
    body: SkillRename,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        return _summary(
            await PersonalSkillService(db, current_user.id).rename_entry(
                skill_id, body.old_path, body.new_path, body.expected_revision
            )
        )
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.delete("/{skill_id}/entry", response_model=SkillSummary)
async def delete_personal_skill_entry(
    skill_id: UUID,
    path: str = Query(...),
    expected_revision: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        return _summary(
            await PersonalSkillService(db, current_user.id).delete_entry(
                skill_id, path, expected_revision
            )
        )
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.get("/{skill_id}/assignments")
async def list_personal_skill_assignments(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        assignments = await PersonalSkillService(db, current_user.id).list_assignments(skill_id)
        return {"agent_ids": [str(item.agent_id) for item in assignments]}
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.post("/{skill_id}/assignments", status_code=status.HTTP_201_CREATED)
async def bind_personal_skill(
    skill_id: UUID,
    body: SkillAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    await _resolve_bindable_agent(db, body.agent_id, current_user)
    try:
        assignment = await PersonalSkillService(db, current_user.id).bind(skill_id, body.agent_id)
        return {"success": True, "agent_id": str(assignment.agent_id)}
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc


@router.delete("/{skill_id}/assignments/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unbind_personal_skill(
    skill_id: UUID,
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(current_active_user),
):
    try:
        await PersonalSkillService(db, current_user.id).unbind(skill_id, agent_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PersonalSkillError as exc:
        raise _http_error(exc) from exc