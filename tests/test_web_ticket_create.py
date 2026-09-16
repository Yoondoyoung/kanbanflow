import re
from datetime import date

import pytest
from sqlmodel import Session

from app.auth import make_csrf_token
from app.models import Sprint, SprintStatus


@pytest.fixture
def active_sprint(make_user, make_project, engine):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    with Session(engine) as session:
        sprint = Sprint(
            project_id=project.id,
            name="Sprint 1",
            goal="Ship it",
            status=SprintStatus.ACTIVE,
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 28),
        )
        session.add(sprint)
        session.commit()
        session.refresh(sprint)
    return owner, project, sprint


def test_modal_targets_the_backlog_column(client, active_sprint, login_as):
    owner, project, sprint = active_sprint
    login_as("ada@example.com")
    page = client.get(f"/projects/{project.slug}").text
    assert 'hx-target="#column-BACKLOG"' in page
    assert 'hx-swap="afterbegin"' in page
    assert f'hx-post="/projects/{project.slug}/tickets"' in page
    assert f'<option value="{sprint.id}" selected>' in page


def test_submitting_the_modal_returns_a_card_fragment(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        f"/projects/{project.slug}/tickets",
        data={
            "title": "Card declines on retry",
            "type": "BUG",
            "description": "Happens on the second attempt",
            "_csrf": make_csrf_token(owner.id),
        },
    )
    assert response.status_code == 201
    assert "<html" not in response.text
    assert response.text.strip().startswith("<article")
    assert "Card declines on retry" in response.text
    assert "#1" in response.text


def test_the_created_ticket_appears_on_the_board(client, active_sprint, login_as):
    owner, project, sprint = active_sprint
    login_as("ada@example.com")
    client.post(
        f"/projects/{project.slug}/tickets",
        data={
            "title": "Visible later",
            "type": "TASK",
            "sprint_id": sprint.id,
            "_csrf": make_csrf_token(owner.id),
        },
    )
    page = client.get(f"/projects/{project.slug}").text
    backlog = page.split('id="column-BACKLOG"')[1].split("</section>")[0]
    assert "Visible later" in backlog


def test_empty_title_is_422(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        f"/projects/{project.slug}/tickets",
        data={"title": "   ", "type": "TASK", "_csrf": make_csrf_token(owner.id)},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/plain")
    assert "<html" not in response.text


def test_non_member_submission_is_403(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    login_as("bob@example.com")
    response = client.post(
        f"/projects/{project.slug}/tickets",
        data={"title": "Sneaky", "type": "TASK", "_csrf": make_csrf_token(bob.id)},
    )
    assert response.status_code == 403


def test_non_member_submission_creates_nothing(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    login_as("bob@example.com")
    client.post(
        f"/projects/{project.slug}/tickets",
        data={"title": "Sneaky", "type": "TASK", "_csrf": make_csrf_token(bob.id)},
    )
    login_as("ada@example.com")
    page = client.get(f"/projects/{project.slug}").text
    assert "Sneaky" not in page


def test_missing_csrf_is_403_and_creates_nothing(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        f"/projects/{project.slug}/tickets",
        data={"title": "No token", "type": "TASK"},
    )
    assert response.status_code == 403
    page = client.get(f"/projects/{project.slug}").text
    assert "No token" not in page


def test_tampered_csrf_is_403_and_creates_nothing(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        f"/projects/{project.slug}/tickets",
        data={"title": "Bad token", "type": "TASK", "_csrf": "tampered.token.value"},
    )
    assert response.status_code == 403
    page = client.get(f"/projects/{project.slug}").text
    assert "Bad token" not in page


def test_five_interactions_or_fewer(client, active_sprint, login_as):
    """Open modal, title, type, description, submit — the form must ask for nothing else."""
    owner, project, _ = active_sprint
    login_as("ada@example.com")
    page = client.get(f"/projects/{project.slug}").text
    modal = page.split('id="ticket-modal"')[1].split("</form>")[0]
    required = re.findall(r"<(?:input|select|textarea)[^>]*\brequired\b[^>]*>", modal)
    assert len(required) <= 2, "only title and type may be required"
