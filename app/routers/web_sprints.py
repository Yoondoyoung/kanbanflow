from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlmodel import Session, select

from app.auth import current_user, project_owner, project_reader, verify_csrf
from app.db import get_session
from app.models import (
    Project,
    ProjectMember,
    Sprint,
    SprintStatus,
    SprintTicketHistory,
    Ticket,
    TicketStatus,
    User,
)
from app.routers.web import render
from app.schemas import SprintCreate
from app.services import close_sprint, create_sprint, start_sprint, update_ticket

router = APIRouter(tags=["web"])
_TICKET_IDS_FORM = Form(...)


def _backlog(
    request: Request,
    session: Session,
    user: User,
    project: Project,
    member: ProjectMember,
    status_code: int = status.HTTP_200_OK,
    **context,
) -> Response:
    planning_sprint = session.exec(
        select(Sprint).where(
            Sprint.project_id == project.id,
            Sprint.status == SprintStatus.PLANNING,
        )
    ).first()
    tickets = session.exec(
        select(Ticket)
        .where(Ticket.project_id == project.id, Ticket.sprint_id.is_(None))
        .order_by(Ticket.ticket_number.desc())
    ).all()
    planning_tickets = (
        session.exec(select(Ticket).where(Ticket.sprint_id == planning_sprint.id)).all()
        if planning_sprint
        else []
    )
    return render(
        request,
        "backlog.html",
        {
            "user": user,
            "project": project,
            "role": member.role.value,
            "active_tab": "backlog",
            "planning_sprint": planning_sprint,
            "planning_ticket_count": len(planning_tickets),
            "planning_points": sum(ticket.story_points or 0 for ticket in planning_tickets),
            "tickets": tickets,
            "sprint": None,
            "ticket_target": "#backlog-tickets",
            "values": {},
            "field_errors": {},
            "error": None,
            **context,
        },
        status_code=status_code,
        session=session,
    )


def _project_sprint(session: Session, project: Project, sprint_id: str) -> Sprint:
    sprint = session.exec(
        select(Sprint).where(Sprint.id == sprint_id, Sprint.project_id == project.id)
    ).first()
    if sprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sprint not found")
    return sprint


def _history_rows(session: Session, sprint_ids: list[str]):
    if not sprint_ids:
        return []
    return session.exec(
        select(SprintTicketHistory, Ticket)
        .join(Ticket, Ticket.id == SprintTicketHistory.ticket_id)
        .where(SprintTicketHistory.sprint_id.in_(sprint_ids))
        .order_by(Ticket.ticket_number)
    ).all()


def _history_delay_total(sprint: Sprint, rows: list[tuple[SprintTicketHistory, Ticket]]) -> int:
    return sum(
        max(0, (sprint.end_date - ticket.first_sprint_entered_at.date()).days)
        for history, ticket in rows
        if not history.was_completed and ticket.first_sprint_entered_at
    )


def _close_preview(
    request: Request,
    session: Session,
    user: User,
    project: Project,
    sprint: Sprint,
    *,
    error: str | None = None,
    selected_next_sprint_id: str = "",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    tickets = session.exec(select(Ticket).where(Ticket.sprint_id == sprint.id)).all()
    planning_sprints = session.exec(
        select(Sprint).where(
            Sprint.project_id == project.id,
            Sprint.status == SprintStatus.PLANNING,
        )
    ).all()
    return render(
        request,
        "partials/sprint_close.html",
        {
            "user": user,
            "project": project,
            "sprint": sprint,
            "planning_sprints": planning_sprints,
            "completed_points": sum(
                ticket.story_points or 0 for ticket in tickets if ticket.status is TicketStatus.DONE
            ),
            "unfinished_count": sum(ticket.status is not TicketStatus.DONE for ticket in tickets),
            "error": error,
            "selected_next_sprint_id": selected_next_sprint_id,
        },
        status_code=status_code,
    )


@router.get("/projects/{slug}/backlog")
def backlog(
    request: Request,
    access: tuple[Project, ProjectMember] = Depends(project_reader),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, member = access
    return _backlog(request, session, user, project, member)


@router.get("/projects/{slug}/sprints")
def sprint_history(
    request: Request,
    access: tuple[Project, ProjectMember] = Depends(project_reader),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, member = access
    sprints = session.exec(
        select(Sprint)
        .where(Sprint.project_id == project.id, Sprint.status == SprintStatus.CLOSED)
        .order_by(Sprint.closed_at.desc(), Sprint.end_date.desc())
    ).all()
    rows_by_sprint = {sprint.id: [] for sprint in sprints}
    for history, ticket in _history_rows(session, [sprint.id for sprint in sprints]):
        rows_by_sprint[history.sprint_id].append((history, ticket))
    summaries = [
        {
            "sprint": sprint,
            "rollover_count": sum(
                not history.was_completed for history, _ in rows_by_sprint[sprint.id]
            ),
            "delay_total": _history_delay_total(sprint, rows_by_sprint[sprint.id]),
        }
        for sprint in sprints
    ]
    return render(
        request,
        "sprint_history.html",
        {
            "user": user,
            "project": project,
            "role": member.role.value,
            "active_tab": "history",
            "summaries": summaries,
        },
        session=session,
    )


@router.get("/projects/{slug}/sprints/{sprint_id}")
def sprint_history_detail(
    sprint_id: str,
    request: Request,
    access: tuple[Project, ProjectMember] = Depends(project_reader),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, member = access
    sprint = _project_sprint(session, project, sprint_id)
    if sprint.status != SprintStatus.CLOSED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sprint not found")
    rows = _history_rows(session, [sprint.id])
    return render(
        request,
        "sprint_history_detail.html",
        {
            "user": user,
            "project": project,
            "role": member.role.value,
            "active_tab": "history",
            "sprint": sprint,
            "history": rows,
            "rollover_count": sum(not entry.was_completed for entry, _ in rows),
            "delay_total": _history_delay_total(sprint, rows),
        },
        session=session,
    )


@router.post("/projects/{slug}/sprints", dependencies=[Depends(verify_csrf)])
def create_sprint_form(
    request: Request,
    name: str = Form(""),
    goal: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    access: tuple[Project, ProjectMember] = Depends(project_owner),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, member = access
    values = {"name": name, "goal": goal, "start_date": start_date, "end_date": end_date}
    try:
        sprint_data = SprintCreate(**values)
        create_sprint(session, project, **sprint_data.model_dump())
    except ValidationError as exc:
        field_errors = {
            error["loc"][-1] if error["loc"] else "form": error["msg"] for error in exc.errors()
        }
        return _backlog(
            request,
            session,
            user,
            project,
            member,
            values=values,
            field_errors=field_errors,
            sprint_form_open=True,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    except HTTPException as exc:
        return _backlog(
            request,
            session,
            user,
            project,
            member,
            values=values,
            error=exc.detail,
            sprint_form_open=True,
            status_code=exc.status_code,
        )
    return RedirectResponse(
        f"/projects/{project.slug}/backlog", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/projects/{slug}/sprints/{sprint_id}/start", dependencies=[Depends(verify_csrf)])
def start_sprint_form(
    sprint_id: str,
    request: Request,
    access: tuple[Project, ProjectMember] = Depends(project_owner),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, member = access
    sprint = _project_sprint(session, project, sprint_id)
    try:
        start_sprint(session, sprint)
    except HTTPException as exc:
        return _backlog(
            request,
            session,
            user,
            project,
            member,
            start_error=exc.detail,
            start_form_open=True,
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/projects/{project.slug}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/projects/{slug}/sprints/{sprint_id}/close")
def close_sprint_preview(
    sprint_id: str,
    request: Request,
    access: tuple[Project, ProjectMember] = Depends(project_owner),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, _ = access
    return _close_preview(
        request, session, user, project, _project_sprint(session, project, sprint_id)
    )


@router.post("/projects/{slug}/sprints/{sprint_id}/close", dependencies=[Depends(verify_csrf)])
def close_sprint_form(
    sprint_id: str,
    request: Request,
    next_sprint_id: str = Form(""),
    access: tuple[Project, ProjectMember] = Depends(project_owner),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, _ = access
    sprint = _project_sprint(session, project, sprint_id)
    if not next_sprint_id:
        return _close_preview(
            request,
            session,
            user,
            project,
            sprint,
            error="Select a planning sprint",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    next_sprint = session.get(Sprint, next_sprint_id)
    if next_sprint is None:
        return _close_preview(
            request,
            session,
            user,
            project,
            sprint,
            error="Select a planning sprint",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        close_sprint(session, sprint, next_sprint)
    except HTTPException as exc:
        return _close_preview(
            request,
            session,
            user,
            project,
            sprint,
            error=exc.detail,
            selected_next_sprint_id=next_sprint_id,
            status_code=exc.status_code,
        )
    target = f"/projects/{project.slug}"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/projects/{slug}/sprints/{sprint_id}/tickets", dependencies=[Depends(verify_csrf)])
def assign_tickets_to_planning_sprint(
    sprint_id: str,
    ticket_ids: list[str] = _TICKET_IDS_FORM,
    access: tuple[Project, ProjectMember] = Depends(project_owner),
    session: Session = Depends(get_session),
) -> Response:
    project, _ = access
    sprint = session.exec(
        select(Sprint).where(
            Sprint.id == sprint_id,
            Sprint.project_id == project.id,
            Sprint.status == SprintStatus.PLANNING,
        )
    ).first()
    if sprint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sprint not found")
    tickets = session.exec(
        select(Ticket).where(
            Ticket.project_id == project.id,
            Ticket.sprint_id.is_(None),
            Ticket.id.in_(ticket_ids),
        )
    ).all()
    if len(tickets) != len(set(ticket_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    try:
        for ticket in tickets:
            update_ticket(session, ticket, project, sprint_id=sprint.id, commit=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return RedirectResponse(
        f"/projects/{project.slug}/backlog", status_code=status.HTTP_303_SEE_OTHER
    )
