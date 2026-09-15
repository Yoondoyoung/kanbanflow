from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlmodel import Session, select

from app.auth import (
    DUMMY_HASH,
    SESSION_COOKIE,
    current_user,
    hash_password,
    load_project_and_membership,
    make_csrf_token,
    optional_user,
    project_writer,
    verify_csrf,
    verify_password,
)
from app.db import get_session
from app.models import Priority, Project, ProjectMember, Ticket, TicketStatus, TicketType, User
from app.routers.api_auth import _set_session
from app.services import create_project, create_ticket

router = APIRouter(tags=["web"])

COLUMNS = (
    TicketStatus.BACKLOG,
    TicketStatus.SELECTED,
    TicketStatus.IN_PROGRESS,
    TicketStatus.DONE,
)

# Reused to give the register form the same EmailStr format check RegisterRequest gives the
# JSON route, without hand-rolling a regex.
_email_adapter = TypeAdapter(EmailStr)

# Hoisted so `Form(...)` isn't called in an argument default (ruff B008).
_DEFAULT_TICKET_TYPE = Form(TicketType.TASK)


def render(request: Request, name: str, context: dict, status_code: int = 200) -> Response:
    from app.main import templates

    user = context.get("user")
    context = {
        "request": request,
        "csrf_token": make_csrf_token(user.id) if user else "",
        **context,
    }
    return templates.TemplateResponse(request, name, context, status_code=status_code)


@router.get("/")
def index(user: User | None = Depends(optional_user)) -> Response:
    target = "/dashboard" if user else "/login"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login")
def login_page(request: Request, user: User | None = Depends(optional_user)) -> Response:
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return render(request, "login.html", {"user": None})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    user = session.exec(select(User).where(User.email == email.lower())).first()
    # Mirror api_auth.login exactly: run verify_password on a real hash even for an unknown
    # email, so bcrypt's cost lands on both branches. Short-circuiting on `user is None` (as
    # the earlier version of this route did) kept the message identical but not the timing --
    # a non-existent account would return in microseconds while a wrong password cost a full
    # bcrypt round, exactly the gap DUMMY_HASH exists to close.
    hashed = user.password_hash if user else DUMMY_HASH
    if not verify_password(password, hashed) or user is None:
        return render(
            request,
            "login.html",
            {"user": None, "error": "Invalid email or password"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_session(response, user.id)
    return response


@router.get("/register")
def register_page(request: Request, user: User | None = Depends(optional_user)) -> Response:
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return render(request, "register.html", {"user": None})


@router.post("/register")
def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    try:
        email = _email_adapter.validate_python(email)
    except ValidationError:
        return render(
            request,
            "register.html",
            {"user": None, "error": "Enter a valid email address"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if len(password) < 8:
        return render(
            request,
            "register.html",
            {"user": None, "error": "Password must be at least 8 characters"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    # hash_password (bcrypt) raises ValueError past 72 UTF-8 bytes; the JSON route catches this
    # in RegisterRequest's validator (app/schemas.py) before it ever reaches hash_password. This
    # form-based route bypasses that schema, so the same guard belongs here too -- otherwise an
    # over-length password crashes with a 500 instead of a normal re-rendered error.
    if len(password.encode("utf-8")) > 72:
        return render(
            request,
            "register.html",
            {"user": None, "error": "Password must be at most 72 bytes"},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if session.exec(select(User).where(User.email == email.lower())).first():
        return render(
            request,
            "register.html",
            {"user": None, "error": "That email is already registered"},
            status_code=status.HTTP_409_CONFLICT,
        )
    user = User(name=name, email=email.lower(), password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    response = RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_session(response, user.id)
    return response


@router.post("/logout")
def logout_submit() -> Response:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _dashboard_context(session: Session, user: User, error: str | None = None) -> dict:
    rows = session.exec(
        select(Project, ProjectMember)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
    ).all()
    context = {
        "user": user,
        "projects": [project for project, _ in rows],
        "roles": {project.id: member.role.value for project, member in rows},
    }
    if error:
        context["error"] = error
    return context


@router.get("/dashboard")
def dashboard(
    request: Request,
    user: User | None = Depends(optional_user),
    session: Session = Depends(get_session),
) -> Response:
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return render(request, "dashboard.html", _dashboard_context(session, user))


@router.post("/projects", dependencies=[Depends(verify_csrf)])
def create_project_form(
    request: Request,
    name: str = Form(...),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    # create_project (app/services.py) is the same function the JSON route
    # (POST /api/v1/projects) calls -- slug derivation, the name limits
    # (Ruling R36, since this form bypasses ProjectCreate entirely), the slug
    # collision check, and the creator-becomes-OWNER membership insert all
    # live there exactly once.
    try:
        project = create_project(session, name, user)
    except HTTPException as exc:
        return render(
            request,
            "dashboard.html",
            _dashboard_context(session, user, error=exc.detail),
            status_code=exc.status_code,
        )
    return RedirectResponse(f"/projects/{project.slug}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/projects/{slug}")
def board(
    slug: str,
    request: Request,
    user: User | None = Depends(optional_user),
    session: Session = Depends(get_session),
) -> Response:
    if user is None:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    # load_project_and_membership already 404s when the project itself is missing; a non-member
    # must get the same 404 rather than learn the project exists, so check member too.
    project, member = load_project_and_membership(slug, user, session)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    tickets = session.exec(
        select(Ticket).where(Ticket.project_id == project.id).order_by(Ticket.ticket_number.desc())
    ).all()
    return render(
        request,
        "board.html",
        {
            "user": user,
            "project": project,
            "role": member.role.value,
            "columns": COLUMNS,
            "tickets_by_status": {
                column.value: [t for t in tickets if t.status == column] for column in COLUMNS
            },
        },
    )


@router.post("/projects/{slug}/tickets", dependencies=[Depends(verify_csrf)])
def create_ticket_form(
    request: Request,
    tasks: BackgroundTasks,
    title: str = Form(...),
    type: TicketType = _DEFAULT_TICKET_TYPE,
    description: str = Form(""),
    project_and_member: tuple[Project, ProjectMember] = Depends(project_writer),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    project, _ = project_and_member
    # create_ticket (app/services.py) is the same function the JSON route calls -- atomic
    # ticket-number allocation, title/description/story_points/meta limits (Ruling R24, since
    # this form bypasses any Pydantic schema), and the TICKET_CREATED notification all live
    # there exactly once.
    try:
        ticket = create_ticket(
            session,
            project,
            user,
            title=title,
            description=description,
            type=type,
            priority=Priority.MEDIUM,
            tasks=tasks,
        )
    except HTTPException as exc:
        # Not a page and not JSON: the modal's error slot renders whatever text comes back
        # (see partials/ticket_modal.html's htmx:after-request handler), so plain text is enough.
        return Response(str(exc.detail), status_code=exc.status_code, media_type="text/plain")
    return render(
        request,
        "partials/ticket_card.html",
        {"user": user, "project": project, "ticket": ticket, "columns": COLUMNS},
        status_code=status.HTTP_201_CREATED,
    )
