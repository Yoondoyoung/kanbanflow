from datetime import date
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.auth import make_csrf_token
from app.models import Sprint, SprintStatus, Ticket
from app.routers import web_sprints


@pytest.fixture
def backlog_world(make_user, make_project, engine):
    owner = make_user(email="ada@example.com")
    member = make_user(email="bob@example.com")
    project = make_project(owner)
    with Session(engine) as session:
        sprint = Sprint(
            project_id=project.id,
            name="Sprint 1",
            goal="Ship it",
            status=SprintStatus.PLANNING,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 28),
        )
        session.add(sprint)
        session.flush()
        unassigned = Ticket(
            ticket_number=1,
            project_id=project.id,
            title="Backlog ticket",
            creator_id=owner.id,
        )
        assigned = Ticket(
            ticket_number=2,
            project_id=project.id,
            sprint_id=sprint.id,
            title="Planned ticket",
            creator_id=owner.id,
        )
        session.add_all([unassigned, assigned])
        session.commit()
        session.refresh(sprint)
        session.refresh(unassigned)
    return SimpleNamespace(
        owner=owner,
        member=member,
        project=project,
        sprint=sprint,
        unassigned=unassigned,
    )


def test_member_can_read_backlog_and_planning_state(client, backlog_world, add_member, login_as):
    add_member(backlog_world.project, backlog_world.member)
    login_as(backlog_world.member.email)

    page = client.get(f"/projects/{backlog_world.project.slug}/backlog")

    assert page.status_code == 200
    assert "Sprint 1" in page.text
    assert "Backlog ticket" in page.text
    assert 'data-testid="owner-planning-controls"' not in page.text


def test_backlog_only_lists_unassigned_tickets(client, backlog_world, login_as):
    login_as(backlog_world.owner.email)

    page = client.get(f"/projects/{backlog_world.project.slug}/backlog")

    assert "Backlog ticket" in page.text
    assert "Planned ticket" not in page.text


def test_owner_creates_a_dated_planning_sprint(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    response = client.post(
        f"/projects/{project.slug}/sprints",
        data={
            "name": "Sprint 1",
            "goal": "Ship it",
            "start_date": "2026-09-21",
            "end_date": "2026-09-28",
            "_csrf": make_csrf_token(owner.id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{project.slug}/backlog"


def test_second_planning_sprint_returns_backlog_conflict(client, backlog_world, login_as):
    login_as(backlog_world.owner.email)

    response = client.post(
        f"/projects/{backlog_world.project.slug}/sprints",
        data={
            "name": "Sprint 2",
            "goal": "More work",
            "start_date": "2026-09-29",
            "end_date": "2026-10-06",
            "_csrf": make_csrf_token(backlog_world.owner.id),
        },
    )

    assert response.status_code == 409
    assert "A planning sprint already exists" in response.text


def test_invalid_sprint_dates_return_a_stable_form_error(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    response = client.post(
        f"/projects/{project.slug}/sprints",
        data={
            "name": "Sprint 1",
            "goal": "Ship it",
            "start_date": "2026-09-28",
            "end_date": "2026-09-21",
            "_csrf": make_csrf_token(owner.id),
        },
    )

    assert response.status_code == 422
    assert "end_date must be after start_date" in response.text
    for value in ("Sprint 1", "Ship it", "2026-09-28", "2026-09-21"):
        assert value in response.text


def test_owner_assigns_multiple_unassigned_tickets_to_planning_sprint(
    client, backlog_world, engine, login_as
):
    with Session(engine) as session:
        another = Ticket(
            ticket_number=3,
            project_id=backlog_world.project.id,
            title="Another backlog ticket",
            creator_id=backlog_world.owner.id,
        )
        session.add(another)
        session.commit()
        session.refresh(another)
    login_as(backlog_world.owner.email)

    response = client.post(
        f"/projects/{backlog_world.project.slug}/sprints/{backlog_world.sprint.id}/tickets",
        data={
            "ticket_ids": [backlog_world.unassigned.id, another.id],
            "_csrf": make_csrf_token(backlog_world.owner.id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    with Session(engine) as session:
        tickets = session.exec(
            select(Ticket).where(Ticket.id.in_([backlog_world.unassigned.id, another.id]))
        ).all()
    assert {ticket.sprint_id for ticket in tickets} == {backlog_world.sprint.id}


def test_assignment_rolls_back_after_a_partial_update(
    client, backlog_world, engine, login_as, monkeypatch
):
    original_update_ticket = web_sprints.update_ticket

    def fail_after_first_update(*args, **kwargs):
        original_update_ticket(*args, **kwargs)
        args[0].flush()
        raise RuntimeError("injected failure")

    monkeypatch.setattr(web_sprints, "update_ticket", fail_after_first_update)
    login_as(backlog_world.owner.email)

    with pytest.raises(RuntimeError, match="injected failure"):
        client.post(
            f"/projects/{backlog_world.project.slug}/sprints/{backlog_world.sprint.id}/tickets",
            data={
                "ticket_ids": backlog_world.unassigned.id,
                "_csrf": make_csrf_token(backlog_world.owner.id),
            },
        )

    with Session(engine) as session:
        ticket = session.get(Ticket, backlog_world.unassigned.id)
    assert ticket.sprint_id is None
    assert ticket.first_sprint_entered_at is None


def test_backlog_nav_marks_the_backlog_tab_current(client, backlog_world, login_as):
    login_as(backlog_world.owner.email)

    page = client.get(f"/projects/{backlog_world.project.slug}/backlog")

    assert f'href="/projects/{backlog_world.project.slug}/backlog" aria-current="page"' in page.text


def test_member_cannot_create_or_assign_sprints(client, backlog_world, add_member, login_as):
    add_member(backlog_world.project, backlog_world.member)
    login_as(backlog_world.member.email)

    create = client.post(
        f"/projects/{backlog_world.project.slug}/sprints",
        data={
            "name": "Sneaky",
            "goal": "Nope",
            "start_date": "2026-09-29",
            "end_date": "2026-10-06",
            "_csrf": make_csrf_token(backlog_world.member.id),
        },
    )
    assign = client.post(
        f"/projects/{backlog_world.project.slug}/sprints/{backlog_world.sprint.id}/tickets",
        data={
            "ticket_ids": backlog_world.unassigned.id,
            "_csrf": make_csrf_token(backlog_world.member.id),
        },
    )

    assert create.status_code == 403
    assert assign.status_code == 403
