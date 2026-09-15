import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import current_user, project_owner, project_reader
from app.db import get_session
from app.models import Project, ProjectMember, Role, Ticket, User, WebhookType
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate

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


@router.get("/{slug}", response_model=ProjectOut)
def get_project(access=Depends(project_reader)):
    project, member = access
    return _out(project, member.role)


@router.patch("/{slug}", response_model=ProjectOut)
def update_project(
    body: ProjectUpdate,
    access=Depends(project_owner),
    session: Session = Depends(get_session),
):
    project, member = access
    if body.name is not None:
        project.name = body.name.strip()
    if body.webhook_type is not None:
        project.webhook_type = body.webhook_type
    if body.webhook_url is not None:
        project.webhook_url = body.webhook_url
    if project.webhook_type != WebhookType.NONE:
        if not project.webhook_url or not project.webhook_url.startswith("https://"):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "webhook_url must be an https URL when webhook_type is set",
            )
    session.add(project)
    session.commit()
    session.refresh(project)
    return _out(project, member.role)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    confirm: str = Query(default=""),
    access=Depends(project_owner),
    session: Session = Depends(get_session),
) -> None:
    project, _ = access
    if confirm != project.slug:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "confirm must equal the slug")
    for ticket in session.exec(select(Ticket).where(Ticket.project_id == project.id)).all():
        session.delete(ticket)
    for member in session.exec(
        select(ProjectMember).where(ProjectMember.project_id == project.id)
    ).all():
        session.delete(member)
    # These models have no ORM relationship() linking them, only FK columns, so
    # SQLAlchemy's unit of work has no dependency info to order the deletes by
    # and will happily try to delete `project` before its children, tripping
    # the FK constraint. An explicit flush forces the child deletes to hit the
    # database first.
    session.flush()
    session.delete(project)
    session.commit()
