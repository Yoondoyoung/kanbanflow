import pytest
from sqlalchemy import JSON, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Project, ProjectMember, Role, Ticket, TicketStatus, TicketType, User


def make_user(session: Session, email: str = "a@b.com") -> User:
    user = User(name="A", email=email, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_foreign_keys_are_enforced(session: Session):
    ticket = Ticket(
        ticket_number=1,
        project_id="does-not-exist",
        title="t",
        type=TicketType.TASK,
        status=TicketStatus.BACKLOG,
        creator_id="also-missing",
    )
    session.add(ticket)
    with pytest.raises(IntegrityError):
        session.commit()


def test_email_is_unique(session: Session):
    make_user(session, "dup@example.com")
    session.add(User(name="B", email="dup@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_member_pair_is_unique(session: Session):
    user = make_user(session)
    project = Project(name="P", slug="p")
    session.add(project)
    session.commit()
    session.refresh(project)
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role=Role.OWNER))
    session.commit()
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role=Role.MEMBER))
    with pytest.raises(IntegrityError):
        session.commit()


def test_ticket_number_is_unique_per_project(session: Session):
    user = make_user(session)
    project = Project(name="P", slug="p")
    session.add(project)
    session.commit()
    session.refresh(project)
    for _ in range(2):
        session.add(
            Ticket(
                ticket_number=7,
                project_id=project.id,
                title="t",
                type=TicketType.TASK,
                status=TicketStatus.BACKLOG,
                creator_id=user.id,
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()


def test_ticket_meta_is_a_non_null_json_column_defaulting_to_empty(session: Session):
    # Spec §4: meta is JSON and NOT NULL with a {} default. The default comes
    # from the model (default_factory), the NOT NULL from the column -- assert
    # both, since patch_ticket's null guard depends on the column being NOT NULL.
    user = make_user(session)
    project = Project(name="P", slug="p")
    session.add(project)
    session.commit()
    session.refresh(project)

    column = Ticket.__table__.c.meta
    assert isinstance(column.type, JSON)
    assert column.nullable is False

    ticket = Ticket(
        ticket_number=1,
        project_id=project.id,
        title="t",
        type=TicketType.TASK,
        status=TicketStatus.BACKLOG,
        creator_id=user.id,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)
    assert ticket.meta == {}

    # NOT NULL is enforced by the database, not just declared on the model.
    # (Assigning Python None through the ORM would *not* trip it: SQLAlchemy's
    # JSON type serialises None to the JSON null literal, which is exactly why
    # patch_ticket has to reject {"meta": null} itself.)
    with pytest.raises(IntegrityError):
        session.exec(text("UPDATE ticket SET meta = NULL WHERE id = :id").bindparams(id=ticket.id))
        session.commit()
