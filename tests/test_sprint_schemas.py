from datetime import date

import pytest
from pydantic import ValidationError

from app.models import SprintStatus, TicketStatus
from app.schemas import (
    SprintClose,
    SprintCreate,
    SprintHistoryOut,
    SprintOut,
    SprintUpdate,
)


def test_sprint_create_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        SprintCreate(
            name="Sprint 1",
            goal="Ship checkout",
            start_date=date(2026, 9, 28),
            end_date=date(2026, 9, 21),
        )


def test_sprint_create_strips_names_and_goals():
    sprint = SprintCreate(
        name="  Sprint 1  ",
        goal="  Ship checkout  ",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
    )

    assert sprint.name == "Sprint 1"
    assert sprint.goal == "Ship checkout"


@pytest.mark.parametrize("field", ["name", "goal"])
def test_sprint_create_rejects_blank_text(field):
    values = {
        "name": "Sprint 1",
        "goal": "Ship checkout",
        "start_date": date(2026, 9, 21),
        "end_date": date(2026, 9, 28),
    }
    values[field] = "   "

    with pytest.raises(ValidationError):
        SprintCreate(**values)


def test_sprint_update_accepts_only_active_status_and_trims_text():
    update = SprintUpdate(name="  Sprint 2 ", goal="  Ship billing ", status=SprintStatus.ACTIVE)

    assert update.name == "Sprint 2"
    assert update.goal == "Ship billing"

    with pytest.raises(ValidationError):
        SprintUpdate(status=SprintStatus.CLOSED)


def test_sprint_update_rejects_blank_text():
    with pytest.raises(ValidationError):
        SprintUpdate(name=" ")


def test_sprint_out_exposes_public_sprint_fields():
    sprint = SprintOut(
        id="sprint-1",
        project_id="project-1",
        name="Sprint 1",
        goal="Ship checkout",
        status=SprintStatus.PLANNING,
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 28),
        committed_points=None,
        completed_points=None,
        closed_at=None,
    )

    assert sprint.id == "sprint-1"
    assert sprint.status is SprintStatus.PLANNING


def test_sprint_close_requires_next_sprint_id():
    assert SprintClose(next_sprint_id="next-sprint").next_sprint_id == "next-sprint"

    with pytest.raises(ValidationError):
        SprintClose()


def test_sprint_history_out_contains_close_snapshot_fields():
    history = SprintHistoryOut(
        ticket_id="ticket-1",
        ticket_number=7,
        title="Checkout",
        status_at_close=TicketStatus.IN_PROGRESS,
        story_points_at_close=3,
        was_completed=False,
    )

    assert history.status_at_close is TicketStatus.IN_PROGRESS
    assert history.was_completed is False
