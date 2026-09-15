import bcrypt
from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Project, ProjectMember, Role, User

SESSION_COOKIE = "kf_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14
_SESSION_SALT = "kf-session"

_serializer = URLSafeTimedSerializer(settings.session_secret, salt=_SESSION_SALT)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # bcrypt raises ValueError for a >72-byte plaintext; fail closed here rather
    # than raise, since login must run to completion even for bad input. Registration
    # enforces the 72-byte limit up front (Task 6's RegisterRequest), so don't add a
    # matching guard to hash_password — that would just duplicate the validation.
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


DUMMY_HASH = hash_password("kanbanflow-dummy-password-for-constant-time-login")


def make_session_cookie(user_id: str) -> str:
    return _serializer.dumps(user_id)


def read_session_cookie(raw: str) -> str | None:
    try:
        return _serializer.loads(raw, max_age=SESSION_MAX_AGE)
    except BadData:
        return None


def optional_user(request: Request, session: Session = Depends(get_session)) -> User | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    user_id = read_session_cookie(raw)
    if user_id is None:
        return None
    return session.get(User, user_id)


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CSRF_FIELD = "_csrf"
CSRF_MAX_AGE = 60 * 60 * 24
_csrf_serializer = URLSafeTimedSerializer(settings.session_secret, salt="kf-csrf")


def make_csrf_token(user_id: str) -> str:
    return _csrf_serializer.dumps(user_id)


def read_csrf_token(raw: str) -> str | None:
    try:
        return _csrf_serializer.loads(raw, max_age=CSRF_MAX_AGE)
    except BadData:
        return None


def assert_csrf_matches(raw: str | None, user_id: str) -> None:
    if not raw or read_csrf_token(raw) != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")


async def verify_csrf(request: Request, user: User = Depends(current_user)) -> None:
    form = await request.form()
    assert_csrf_matches(form.get(CSRF_FIELD), user.id)


def load_project_and_membership(
    slug: str, user: User, session: Session
) -> tuple[Project, ProjectMember | None]:
    project = session.exec(select(Project).where(Project.slug == slug)).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    member = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    ).first()
    return project, member


def project_reader(
    slug: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> tuple[Project, ProjectMember]:
    project, member = load_project_and_membership(slug, user, session)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project, member


def require_member(member: ProjectMember | None) -> ProjectMember:
    """The one place a missing membership becomes 403 on a write path. Every
    write-side dependency or helper -- whether it starts from a slug
    (project_writer) or a ticket id (api_tickets.load_ticket_for_write) --
    routes through this instead of re-deciding the status itself."""
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a project member")
    return member


def project_writer(
    slug: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> tuple[Project, ProjectMember]:
    project, member = load_project_and_membership(slug, user, session)
    return project, require_member(member)


def project_owner(
    slug: str, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> tuple[Project, ProjectMember]:
    project, member = project_writer(slug, user, session)
    if member.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner role required")
    return project, member
