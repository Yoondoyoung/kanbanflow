import json

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session, select

from app.models import (
    Priority,
    Project,
    ProjectMember,
    Ticket,
    TicketStatus,
    TicketType,
    User,
    utcnow,
)

META_MAX_BYTES = 8 * 1024
META_MAX_DEPTH = 3
TITLE_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 20_000
VALID_STORY_POINTS = {1, 2, 3, 5, 8, 13}


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
    return ticket


def set_status(
    session: Session,
    ticket: Ticket,
    new_status: TicketStatus,
    resolution_notes: str | None = None,
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
    return ticket
