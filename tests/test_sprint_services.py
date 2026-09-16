from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models import Sprint, SprintStatus, Ticket
from app.services import create_sprint, start_sprint, update_sprint


def test_create_sprint_creates_a_planning_sprint(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)

    sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    assert sprint.status is SprintStatus.PLANNING
    assert sprint.project_id == project.id


def test_create_sprint_rejects_a_second_planning_sprint(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    with pytest.raises(HTTPException) as exc_info:
        create_sprint(
            session,
            project,
            name="Sprint 2",
            goal="Ship billing",
            start_date=date(2026, 9, 29),
            end_date=date(2026, 10, 6),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "A planning sprint already exists"


@pytest.mark.parametrize("end_date", [date(2026, 9, 21), date(2026, 9, 28)])
def test_create_sprint_rejects_invalid_dates(session, make_user, make_project, end_date):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)

    with pytest.raises(HTTPException) as exc_info:
        create_sprint(
            session,
            project,
            name="Sprint 1",
            goal="Ship checkout",
            start_date=date(2026, 9, 28),
            end_date=end_date,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "end_date must be after start_date"


def test_update_sprint_changes_planning_details(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    updated = update_sprint(
        session,
        sprint,
        name="Sprint 2",
        goal="Ship billing",
        start_date=date(2026, 9, 22),
        end_date=date(2026, 9, 29),
    )

    assert (updated.name, updated.goal) == ("Sprint 2", "Ship billing")
    assert (updated.start_date, updated.end_date) == (date(2026, 9, 22), date(2026, 9, 29))


@pytest.mark.parametrize(
    "changes", [{"start_date": date(2026, 9, 28)}, {"end_date": date(2026, 9, 21)}]
)
def test_update_sprint_rejects_invalid_one_sided_date_changes(
    session, make_user, make_project, changes
):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    with pytest.raises(HTTPException) as exc_info:
        update_sprint(session, sprint, **changes)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "end_date must be after start_date"


def test_update_sprint_rejects_non_planning_sprints(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = Sprint(
        project_id=project.id,
        name="Sprint 1",
        goal="Ship checkout",
        status=SprintStatus.ACTIVE,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )
    session.add(sprint)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        update_sprint(session, sprint, name="Changed")

    assert exc_info.value.status_code == 409
    session.refresh(sprint)
    assert sprint.name == "Sprint 1"


@pytest.mark.parametrize(
    "changes", [{"name": None}, {"goal": None}, {"start_date": None}, {"end_date": None}]
)
def test_update_sprint_rejects_null_required_fields(session, make_user, make_project, changes):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    with pytest.raises(HTTPException) as exc_info:
        update_sprint(session, sprint, **changes)

    assert exc_info.value.status_code == 422
    session.refresh(sprint)
    assert (sprint.name, sprint.goal, sprint.start_date, sprint.end_date) == (
        "Sprint 1",
        "Ship checkout",
        date(2026, 9, 21),
        date(2026, 9, 28),
    )


def test_update_sprint_rolls_back_an_integrity_error(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    def fail_commit(_session):
        raise IntegrityError("UPDATE", {}, RuntimeError("simulated update conflict"))

    event.listen(session, "before_commit", fail_commit)
    try:
        with pytest.raises(HTTPException) as exc_info:
            update_sprint(session, sprint, name="Changed")
    finally:
        event.remove(session, "before_commit", fail_commit)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Sprint update conflict"
    session.refresh(sprint)
    assert sprint.name == "Sprint 1"
    assert update_sprint(session, sprint, name="Changed").name == "Changed"


def test_start_sprint_freezes_committed_points(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    planning_sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )
    session.add_all(
        [
            Ticket(
                ticket_number=1,
                project_id=project.id,
                sprint_id=planning_sprint.id,
                title="Complete checkout",
                story_points=5,
                creator_id=owner.id,
            ),
            Ticket(
                ticket_number=2,
                project_id=project.id,
                sprint_id=planning_sprint.id,
                title="Unestimated",
                creator_id=owner.id,
            ),
        ]
    )
    session.commit()

    started = start_sprint(session, planning_sprint)

    assert started.status is SprintStatus.ACTIVE
    assert started.committed_points == 5


def test_start_sprint_rejects_a_second_active_sprint(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    active = Sprint(
        project_id=project.id,
        name="Sprint 1",
        goal="Ship checkout",
        status=SprintStatus.ACTIVE,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )
    session.add(active)
    session.commit()
    planning = create_sprint(
        session,
        project,
        name="Sprint 2",
        goal="Ship billing",
        start_date=date(2026, 9, 29),
        end_date=date(2026, 10, 6),
    )

    with pytest.raises(HTTPException) as exc_info:
        start_sprint(session, planning)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "An active sprint already exists"
    session.refresh(planning)
    assert planning.status is SprintStatus.PLANNING


def test_start_sprint_requires_a_planning_sprint(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = Sprint(
        project_id=project.id,
        name="Sprint 1",
        goal="Ship checkout",
        status=SprintStatus.CLOSED,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )
    session.add(sprint)
    session.commit()

    with pytest.raises(HTTPException) as exc_info:
        start_sprint(session, sprint)

    assert exc_info.value.status_code == 409


def test_create_sprint_rolls_back_a_planning_index_race(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)

    def fail_commit(_session):
        raise IntegrityError("INSERT", {}, RuntimeError("simulated planning race"))

    event.listen(session, "before_commit", fail_commit)
    try:
        with pytest.raises(HTTPException) as exc_info:
            create_sprint(
                session,
                project,
                name="Sprint 1",
                goal="Ship checkout",
                start_date=date(2026, 9, 21),
                end_date=date(2026, 9, 28),
            )
    finally:
        event.remove(session, "before_commit", fail_commit)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "A planning sprint already exists"
    assert session.exec(select(Sprint)).first() is None


def test_start_sprint_rolls_back_an_active_index_race(session, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    sprint = create_sprint(
        session,
        project,
        name="Sprint 1",
        goal="Ship checkout",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    def fail_commit(_session):
        raise IntegrityError("UPDATE", {}, RuntimeError("simulated active race"))

    event.listen(session, "before_commit", fail_commit)
    try:
        with pytest.raises(HTTPException) as exc_info:
            start_sprint(session, sprint)
    finally:
        event.remove(session, "before_commit", fail_commit)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "An active sprint already exists"
    session.refresh(sprint)
    assert sprint.status is SprintStatus.PLANNING
