from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlmodel import Session, select

from app.auth import current_user, project_owner, project_reader, verify_csrf
from app.db import get_session
from app.models import Project, ProjectMember, Sprint, SprintStatus, Ticket, User
from app.routers.web import render
from app.schemas import SprintCreate
from app.services import create_sprint, update_ticket

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
    return render(
        request,
        "backlog.html",
        {
            "user": user,
            "project": project,
            "role": member.role.value,
            "planning_sprint": planning_sprint,
            "tickets": tickets,
            "values": {},
            "field_errors": {},
            "error": None,
            **context,
        },
        status_code=status_code,
        session=session,
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
        field_errors = {error["loc"][-1]: error["msg"] for error in exc.errors()}
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
    for ticket in tickets:
        update_ticket(session, ticket, project, sprint_id=sprint.id)
    return RedirectResponse(
        f"/projects/{project.slug}/backlog", status_code=status.HTTP_303_SEE_OTHER
    )
