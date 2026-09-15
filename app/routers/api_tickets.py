from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.auth import _load, current_user
from app.db import get_session
from app.models import Project, Ticket, User
from app.schemas import TicketCreate, TicketOut
from app.services import create_ticket

router = APIRouter(prefix="/api/v1", tags=["tickets"])


def _project_for_write(slug: str, user: User, session: Session) -> Project:
    project, member = _load(slug, user, session)
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a project member")
    return project


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def post_ticket(
    body: TicketCreate,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Ticket:
    project = _project_for_write(body.slug, user, session)
    return create_ticket(
        session,
        project,
        user,
        title=body.title,
        description=body.description,
        type=body.type,
        priority=body.priority,
        story_points=body.story_points,
        assignee_id=body.assignee_id,
        meta=body.meta,
    )
