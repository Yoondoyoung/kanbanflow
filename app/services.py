import json
import re
from datetime import date

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.auth import hash_password
from app.models import (
    Priority,
    Project,
    ProjectMember,
    Role,
    Sprint,
    SprintStatus,
    SprintTicketHistory,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    utcnow,
)
from app.notifications import EVENT_TICKET_CREATED, EVENT_TICKET_DONE, schedule

META_MAX_BYTES = 8 * 1024
META_MAX_DEPTH = 3
TITLE_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 20_000
VALID_STORY_POINTS = {1, 2, 3, 5, 8, 13}
NAME_MAX_LENGTH = 100
USER_NAME_MAX_LENGTH = 50
_EMAIL_TAKEN = "Email already registered"
_PLANNING_SPRINT_EXISTS = "A planning sprint already exists"
_ACTIVE_SPRINT_EXISTS = "An active sprint already exists"
_SPRINT_UPDATE_CONFLICT = "Sprint update conflict"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50].strip("-")


def _slug_conflict_detail(slug: str) -> str:
    return f"Slug already taken: {slug}"


def register_user(session: Session, *, name: str, email: str, password: str) -> User:
    # Both registration routes use this service because the HTML form has no
    # Pydantic model in front of it. Keep the database-facing validation and
    # duplicate-email race handling in one place.
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "name must not be blank")
    if len(clean_name) > USER_NAME_MAX_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"name must be at most {USER_NAME_MAX_LENGTH} characters",
        )
    normalized_email = email.lower()
    if session.exec(select(User).where(User.email == normalized_email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, _EMAIL_TAKEN)
    user = User(
        name=clean_name,
        email=normalized_email,
        password_hash=hash_password(password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        # The unique constraint resolves a concurrent check-then-insert race.
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _EMAIL_TAKEN) from None
    session.refresh(user)
    return user


def create_project(session: Session, name: str, user: User) -> Project:
    # Shared by the JSON route (app/routers/api_projects.py) and the dashboard
    # form (app/routers/web.py) so slug derivation, the collision pre-check, the
    # IntegrityError race guard (Ruling R16), and the creator-becomes-OWNER
    # membership insert exist in exactly one place. ProjectCreate already
    # enforces these name limits on the JSON path via Pydantic; the form route
    # has no schema in front of it (Ruling R36), so the check lives here where
    # both callers get it.
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "name must not be blank")
    if len(clean_name) > NAME_MAX_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"name must be at most {NAME_MAX_LENGTH} characters",
        )
    slug = slugify(clean_name)
    if not slug:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Name yields an empty slug")
    if session.exec(select(Project).where(Project.slug == slug)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, _slug_conflict_detail(slug))
    project = Project(name=clean_name, slug=slug)
    session.add(project)
    try:
        session.flush()
        session.add(ProjectMember(project_id=project.id, user_id=user.id, role=Role.OWNER))
        session.commit()
    except IntegrityError:
        # Two concurrent project creations that derive the same slug can both
        # pass the pre-check above; the unique constraint on Project.slug
        # catches the loser here (Ruling R16).
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _slug_conflict_detail(slug)) from None
    session.refresh(project)
    return project


def create_sprint(
    session: Session,
    project: Project,
    *,
    name: str,
    goal: str,
    start_date: date,
    end_date: date,
) -> Sprint:
    if end_date <= start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date must be after start_date"
        )
    if session.exec(
        select(Sprint).where(
            Sprint.project_id == project.id,
            Sprint.status == SprintStatus.PLANNING,
        )
    ).first():
        raise HTTPException(status.HTTP_409_CONFLICT, _PLANNING_SPRINT_EXISTS)
    sprint = Sprint(
        project_id=project.id,
        name=name,
        goal=goal,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(sprint)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _PLANNING_SPRINT_EXISTS) from None
    session.refresh(sprint)
    return sprint


def update_sprint(session: Session, sprint: Sprint, **changes) -> Sprint:
    if sprint.status is not SprintStatus.PLANNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sprint must be planning")
    for field in ("name", "goal", "start_date", "end_date"):
        if field in changes and changes[field] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field} may not be null")
    start_date = changes.get("start_date", sprint.start_date)
    end_date = changes.get("end_date", sprint.end_date)
    if end_date <= start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "end_date must be after start_date"
        )
    for field in ("name", "goal", "start_date", "end_date"):
        if field in changes:
            setattr(sprint, field, changes[field])
    session.add(sprint)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _SPRINT_UPDATE_CONFLICT) from None
    session.refresh(sprint)
    return sprint


def start_sprint(session: Session, sprint: Sprint) -> Sprint:
    if sprint.status is not SprintStatus.PLANNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sprint must be planning")
    if session.exec(
        select(Sprint).where(
            Sprint.project_id == sprint.project_id,
            Sprint.status == SprintStatus.ACTIVE,
        )
    ).first():
        raise HTTPException(status.HTTP_409_CONFLICT, _ACTIVE_SPRINT_EXISTS)
    sprint.committed_points = sum(
        points or 0
        for points in session.exec(select(Ticket.story_points).where(Ticket.sprint_id == sprint.id))
    )
    sprint.status = SprintStatus.ACTIVE
    session.add(sprint)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _ACTIVE_SPRINT_EXISTS) from None
    session.refresh(sprint)
    return sprint


def close_sprint(session: Session, sprint: Sprint, next_sprint: Sprint) -> Sprint:
    if sprint.status is not SprintStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sprint must be active")
    if next_sprint.project_id != sprint.project_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Next sprint must belong to the same project")
    if next_sprint.status is not SprintStatus.PLANNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Next sprint must be planning")

    tickets = session.exec(select(Ticket).where(Ticket.sprint_id == sprint.id)).all()
    try:
        completed_points = 0
        for ticket in tickets:
            session.add(
                SprintTicketHistory(
                    sprint_id=sprint.id,
                    ticket_id=ticket.id,
                    status_at_close=ticket.status,
                    story_points_at_close=ticket.story_points,
                    was_completed=ticket.status is TicketStatus.DONE,
                )
            )
            if ticket.status is TicketStatus.DONE:
                completed_points += ticket.story_points or 0

        for ticket in tickets:
            if ticket.status is TicketStatus.DONE:
                continue
            ticket.sprint_id = next_sprint.id
            ticket.rollover_count += 1
            ticket.delayed_days = (
                max(0, (sprint.end_date - ticket.first_sprint_entered_at.date()).days)
                if ticket.first_sprint_entered_at is not None
                else None
            )

        sprint.completed_points = completed_points
        sprint.status = SprintStatus.CLOSED
        sprint.closed_at = utcnow()
        session.add(sprint)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(sprint)
    return sprint


def _depth(value, level: int = 1) -> int:
    if isinstance(value, dict):
        return max((_depth(v, level + 1) for v in value.values()), default=level)
    if isinstance(value, list):
        return max((_depth(v, level + 1) for v in value), default=level)
    return level - 1


def validate_meta(meta) -> None:
    if not isinstance(meta, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "meta must be a JSON object")
    if _depth(meta) > META_MAX_DEPTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"meta may not nest deeper than {META_MAX_DEPTH} levels",
        )
    if len(json.dumps(meta).encode("utf-8")) > META_MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "meta exceeds 8 KB")


def validate_assignee(session: Session, project: Project, assignee_id: str | None) -> None:
    if assignee_id is None:
        return
    member = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == assignee_id,
        )
    ).first()
    if member is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "assignee must be a project member"
        )


def allocate_ticket_number(session: Session, project_id: str) -> int:
    # Atomic per-project counter: UPDATE ... RETURNING runs inside the
    # caller's open transaction, alongside the ticket insert that follows.
    # A SELECT MAX(ticket_number) + 1 would read a value another concurrent
    # writer could be about to take; this claims the number as part of the
    # same write. Because it shares the transaction with the insert, a
    # rollback (e.g. the insert violates a constraint) undoes the increment
    # too, so the sequence stays gapless, not just unique.
    row = session.exec(
        text(
            "UPDATE project SET next_ticket_number = next_ticket_number + 1 "
            "WHERE id = :project_id RETURNING next_ticket_number - 1"
        ).bindparams(project_id=project_id)
    ).one()
    return int(row[0])


def create_ticket(
    session: Session,
    project: Project,
    creator: User,
    *,
    title: str,
    description: str = "",
    type: TicketType = TicketType.TASK,
    priority: Priority = Priority.MEDIUM,
    story_points: int | None = None,
    assignee_id: str | None = None,
    meta: dict | None = None,
    tasks: BackgroundTasks | None = None,
) -> Ticket:
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "title must not be empty")
    if len(clean_title) > TITLE_MAX_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"title must be at most {TITLE_MAX_LENGTH} characters",
        )
    if len(description) > DESCRIPTION_MAX_LENGTH:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"description must be at most {DESCRIPTION_MAX_LENGTH} characters",
        )
    if story_points is not None and story_points not in VALID_STORY_POINTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "story_points must be one of 1, 2, 3, 5, 8, 13",
        )
    if meta is None:
        meta = {}
    validate_meta(meta)
    validate_assignee(session, project, assignee_id)
    ticket = Ticket(
        ticket_number=allocate_ticket_number(session, project.id),
        project_id=project.id,
        title=clean_title,
        description=description,
        type=type,
        status=TicketStatus.BACKLOG,
        priority=priority,
        story_points=story_points,
        creator_id=creator.id,
        assignee_id=assignee_id,
        meta=meta,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    schedule(tasks, project, EVENT_TICKET_CREATED, ticket)
    return ticket


def set_status(
    session: Session,
    ticket: Ticket,
    new_status: TicketStatus,
    resolution_notes: str | None = None,
    *,
    project: Project | None = None,
    tasks: BackgroundTasks | None = None,
) -> Ticket:
    # Any status may move to any other; there is no transition graph to
    # enforce. completed_at tracks DONE membership: entering DONE stamps it,
    # leaving clears it. Re-affirming DONE (a double-clicked dropdown) must
    # not restamp it to a new timestamp, so only stamp when not already DONE.
    if new_status == TicketStatus.DONE:
        if ticket.completed_at is None:
            ticket.completed_at = utcnow()
    else:
        ticket.completed_at = None
    ticket.status = new_status
    # resolution_notes is only overwritten when the request supplies one; it
    # is never cleared as a side effect of leaving DONE (ADR: losing an
    # author's note to a mis-clicked dropdown is worse than a stale one).
    if resolution_notes is not None:
        ticket.resolution_notes = resolution_notes
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    if new_status == TicketStatus.DONE and project is not None:
        schedule(tasks, project, EVENT_TICKET_DONE, ticket)
    return ticket
