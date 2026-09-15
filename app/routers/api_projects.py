import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import current_user
from app.db import get_session
from app.models import Project, ProjectMember, Role, User
from app.schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50].strip("-")


def _slug_conflict_detail(slug: str) -> str:
    return f"Slug already taken: {slug}"


def _out(project: Project, role: Role | None) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        slug=project.slug,
        webhook_type=project.webhook_type,
        webhook_url=project.webhook_url,
        created_at=project.created_at,
        role=role.value if role else None,
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
):
    slug = slugify(body.name)
    if not slug:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name yields an empty slug")
    if session.exec(select(Project).where(Project.slug == slug)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, _slug_conflict_detail(slug))
    project = Project(name=body.name.strip(), slug=slug)
    session.add(project)
    try:
        session.flush()
        session.add(ProjectMember(project_id=project.id, user_id=user.id, role=Role.OWNER))
        session.commit()
    except IntegrityError:
        # Two concurrent project creations that derive the same slug can both
        # pass the pre-check above (routes run sync in FastAPI's threadpool,
        # so this is a real race, not a theoretical one). The unique
        # constraint on Project.slug catches the loser here; turn that into
        # the same 409 the pre-check gives the common case, not an unhandled
        # 500.
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _slug_conflict_detail(slug)) from None
    session.refresh(project)
    return _out(project, Role.OWNER)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user: User = Depends(current_user), session: Session = Depends(get_session)
) -> list[ProjectOut]:
    rows = session.exec(
        select(Project, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    ).all()
    return [_out(project, member.role) for project, member in rows]
