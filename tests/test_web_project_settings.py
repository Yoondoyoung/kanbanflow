from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.auth import make_csrf_token
from app.models import Project, ProjectMember, Role, WebhookType


@pytest.fixture
def settings_world(make_user, make_project, add_member):
    owner = make_user(email="ada@example.com")
    member = make_user(email="bob@example.com")
    candidate = make_user(email="cam@example.com")
    project = make_project(owner, name="Payment Gateway")
    add_member(project, member)
    return SimpleNamespace(owner=owner, member=member, candidate=candidate, project=project)


def _csrf(user):
    return {"_csrf": make_csrf_token(user.id)}


def test_owner_sees_project_webhook_and_member_controls(client, settings_world, login_as):
    login_as(settings_world.owner.email)

    page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert page.status_code == 200
    assert "Project settings" in page.text
    assert "Payment Gateway" in page.text
    assert "ada@example.com" in page.text
    assert "bob@example.com" in page.text
    assert 'data-testid="owner-settings-controls"' in page.text
    assert 'name="webhook_url"' in page.text
    assert 'name="confirm"' in page.text


def test_member_reads_settings_without_mutation_controls_or_webhook_secret(
    client, settings_world, engine, login_as
):
    with Session(engine) as session:
        project = session.get(Project, settings_world.project.id)
        project.webhook_type = WebhookType.SLACK
        project.webhook_url = "https://hooks.example.test/secret"
        session.add(project)
        session.commit()
    login_as(settings_world.member.email)

    page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert page.status_code == 200
    assert "Payment Gateway" in page.text
    assert "ada@example.com" in page.text
    assert "Configured" in page.text
    assert "https://hooks.example.test/secret" not in page.text
    assert 'data-testid="owner-settings-controls"' not in page.text
    assert f'action="/projects/{settings_world.project.slug}/settings/' not in page.text


def test_owner_renames_project_without_changing_its_slug(client, settings_world, engine, login_as):
    login_as(settings_world.owner.email)

    response = client.post(
        f"/projects/{settings_world.project.slug}/settings/project",
        data={"name": "Checkout", **_csrf(settings_world.owner)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/projects/{settings_world.project.slug}/settings"
    with Session(engine) as session:
        project = session.get(Project, settings_world.project.id)
    assert (project.name, project.slug) == ("Checkout", "payment-gateway")


def test_webhook_validation_re_renders_settings(client, settings_world, login_as):
    login_as(settings_world.owner.email)

    response = client.post(
        f"/projects/{settings_world.project.slug}/settings/project",
        data={
            "name": "<b>Changed</b>",
            "webhook_type": "SLACK",
            "webhook_url": "https://",
            **_csrf(settings_world.owner),
        },
    )

    assert response.status_code == 422
    assert "http(s) URL" in response.text
    assert "&lt;b&gt;Changed&lt;/b&gt;" in response.text
    assert "<b>Changed</b>" not in response.text
    assert 'value="https://"' in response.text


def test_member_api_redacts_webhook_but_owner_can_read_it(client, settings_world, engine, login_as):
    secret = "https://hooks.example.test/secret"
    with Session(engine) as session:
        project = session.get(Project, settings_world.project.id)
        project.webhook_type = WebhookType.SLACK
        project.webhook_url = secret
        session.add(project)
        session.commit()

    login_as(settings_world.member.email)
    member_project = client.get(f"/api/v1/projects/{settings_world.project.slug}")
    member_list = client.get("/api/v1/projects")

    assert member_project.status_code == 200
    assert member_project.json()["webhook_url"] is None
    assert member_list.json()[0]["webhook_url"] is None

    client.post("/api/v1/auth/logout")
    login_as(settings_world.owner.email)
    owner_project = client.get(f"/api/v1/projects/{settings_world.project.slug}")
    owner_page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert owner_project.json()["webhook_url"] == secret
    assert secret in owner_page.text


def test_owner_adds_changes_and_removes_members(client, settings_world, engine, login_as):
    login_as(settings_world.owner.email)

    added = client.post(
        f"/projects/{settings_world.project.slug}/settings/members",
        data={
            "email": settings_world.candidate.email,
            "role": "MEMBER",
            **_csrf(settings_world.owner),
        },
        follow_redirects=False,
    )
    changed = client.post(
        f"/projects/{settings_world.project.slug}/settings/members/{settings_world.member.id}",
        data={"role": "OWNER", **_csrf(settings_world.owner)},
        follow_redirects=False,
    )
    removed = client.post(
        f"/projects/{settings_world.project.slug}/settings/members/{settings_world.candidate.id}/remove",
        data=_csrf(settings_world.owner),
        follow_redirects=False,
    )

    assert (added.status_code, changed.status_code, removed.status_code) == (303, 303, 303)
    with Session(engine) as session:
        rows = session.exec(
            select(ProjectMember).where(ProjectMember.project_id == settings_world.project.id)
        ).all()
    assert {(row.user_id, row.role) for row in rows} == {
        (settings_world.owner.id, Role.OWNER),
        (settings_world.member.id, Role.OWNER),
    }


def test_settings_preserves_last_owner_and_requires_csrf(client, settings_world, login_as):
    login_as(settings_world.owner.email)

    missing_csrf = client.post(
        f"/projects/{settings_world.project.slug}/settings/members/{settings_world.owner.id}",
        data={"role": "MEMBER"},
    )
    last_owner = client.post(
        f"/projects/{settings_world.project.slug}/settings/members/{settings_world.owner.id}",
        data={"role": "MEMBER", **_csrf(settings_world.owner)},
    )

    assert missing_csrf.status_code == 403
    assert last_owner.status_code == 409
    assert "at least one OWNER" in last_owner.text


def test_project_delete_requires_immutable_slug_confirmation(
    client, settings_world, engine, login_as
):
    login_as(settings_world.owner.email)

    denied = client.post(
        f"/projects/{settings_world.project.slug}/settings/delete",
        data={"confirm": "Payment Gateway", **_csrf(settings_world.owner)},
    )
    deleted = client.post(
        f"/projects/{settings_world.project.slug}/settings/delete",
        data={"confirm": settings_world.project.slug, **_csrf(settings_world.owner)},
        follow_redirects=False,
    )

    assert denied.status_code == 422
    assert "confirm must equal the slug" in denied.text
    assert deleted.status_code == 303
    with Session(engine) as session:
        assert session.get(Project, settings_world.project.id) is None
