from types import SimpleNamespace

import pytest
from fastapi import Response
from sqlmodel import Session, select

import app.routers.web_sprints as web_sprints
from app.auth import make_csrf_token
from app.models import Project, ProjectMember, Role, WebhookType
from app.services import chat_webhooks, set_chat_webhook


@pytest.fixture
def settings_world(make_user, make_project, add_member):
    owner = make_user(email="ada@example.com", name="Ada")
    member = make_user(email="bob@example.com", name="Bob")
    candidate = make_user(email="cam@example.com")
    project = make_project(owner, name="Payment Gateway")
    add_member(project, member)
    return SimpleNamespace(owner=owner, member=member, candidate=candidate, project=project)


def _csrf(user):
    return {"_csrf": make_csrf_token(user.id)}


def test_owner_sees_integration_and_member_controls(client, settings_world, login_as):
    login_as(settings_world.owner.email)

    page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert page.status_code == 200
    assert "Project settings" in page.text
    assert "Payment Gateway" in page.text
    assert "ada@example.com" in page.text
    assert "bob@example.com" in page.text
    assert 'data-testid="owner-settings-controls"' in page.text
    assert 'name="url"' in page.text
    assert all(provider in page.text for provider in ("Slack", "Teams", "Discord", "GitHub"))
    assert "Coming soon" in page.text
    assert 'name="confirm"' in page.text


def test_settings_member_controls_name_members_and_use_a_danger_action(
    client, settings_world, login_as
):
    """Removing a member name or danger styling must make this fail."""
    login_as(settings_world.owner.email)

    page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert 'aria-label="Role for Bob"' in page.text
    assert 'aria-label="Change role for Bob"' in page.text
    assert 'aria-label="Remove Bob"' in page.text
    assert '<label class="sr-only" for="add-member-role">Role for new member</label>' in page.text
    assert 'action="/projects/payment-gateway/settings/delete"' in page.text
    assert (
        'class="app-danger-button" type="submit" aria-label="Remove Bob">Remove</button>'
        in page.text
    )
    assert 'class="app-danger-button" type="submit">Delete project</button>' in page.text


def test_project_settings_save_redirects_to_a_textual_status(
    client, settings_world, login_as
):
    login_as(settings_world.owner.email)

    response = client.post(
        f"/projects/{settings_world.project.slug}/settings/project",
        data={"name": "Checkout", **_csrf(settings_world.owner)},
        follow_redirects=False,
    )

    assert response.headers["location"] == (
        f"/projects/{settings_world.project.slug}/settings?saved=1"
    )
    page = client.get(response.headers["location"])
    assert '<p class="form-status" role="status">Settings saved.</p>' in page.text


def test_member_reads_settings_without_mutation_controls_or_webhook_secret(
    client, settings_world, session, login_as
):
    project = session.get(Project, settings_world.project.id)
    set_chat_webhook(
        session, project, WebhookType.SLACK, "https://hooks.example.test/secret"
    )
    login_as(settings_world.member.email)

    page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert page.status_code == 200
    assert "Payment Gateway" in page.text
    assert "ada@example.com" in page.text
    assert "Connected" in page.text
    assert "https://hooks.example.test/secret" not in page.text
    assert 'name="url"' not in page.text
    assert 'data-testid="owner-settings-controls"' not in page.text
    assert f'action="/projects/{settings_world.project.slug}/settings/' not in page.text


def test_settings_template_context_contains_only_chat_provider_status(
    client, settings_world, session, login_as, monkeypatch
):
    project = session.get(Project, settings_world.project.id)
    secret = "https://hooks.example.test/context-secret"
    set_chat_webhook(session, project, WebhookType.SLACK, secret)
    captured = {}

    def capture_render(request, name, context, **kwargs):
        captured.update(context)
        return Response()

    monkeypatch.setattr(web_sprints, "render", capture_render)
    login_as(settings_world.owner.email)

    response = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert response.status_code == 200
    assert captured["chat_integrations"] == {"SLACK": True}
    assert secret not in repr(captured["chat_integrations"])


def test_owner_renames_project_without_changing_its_slug(client, settings_world, engine, login_as):
    login_as(settings_world.owner.email)

    response = client.post(
        f"/projects/{settings_world.project.slug}/settings/project",
        data={"name": "Checkout", **_csrf(settings_world.owner)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/projects/{settings_world.project.slug}/settings?saved=1"
    )
    with Session(engine) as session:
        project = session.get(Project, settings_world.project.id)
    assert (project.name, project.slug) == ("Checkout", "payment-gateway")


def test_chat_webhook_validation_re_renders_settings_without_url(
    client, settings_world, login_as
):
    login_as(settings_world.owner.email)

    response = client.post(
        f"/projects/{settings_world.project.slug}/settings/integrations/SLACK",
        data={
            "url": "https://",
            **_csrf(settings_world.owner),
        },
    )

    assert response.status_code == 422
    assert "safe https URL" in response.text
    assert 'value="https://"' not in response.text


def test_chat_integration_routes_are_owner_only_and_never_render_secret(
    client, settings_world, session, login_as
):
    secret = "https://hooks.example.test/secret"
    project = session.get(Project, settings_world.project.id)
    set_chat_webhook(session, project, WebhookType.SLACK, secret)
    member_url = f"/projects/{settings_world.project.slug}/settings/integrations/SLACK"
    disconnect_url = f"{member_url}/disconnect"

    login_as(settings_world.member.email)
    assert client.post(
        member_url,
        data={"url": "https://hooks.example.test/x", **_csrf(settings_world.member)},
    ).status_code == 403
    member_page = client.get(f"/projects/{settings_world.project.slug}/settings")
    assert "Slack" in member_page.text
    assert "Connected" in member_page.text
    assert 'name="url"' not in member_page.text

    client.post("/api/v1/auth/logout")
    login_as(settings_world.owner.email)
    owner_project = client.get(f"/api/v1/projects/{settings_world.project.slug}")
    owner_page = client.get(f"/projects/{settings_world.project.slug}/settings")

    assert "webhook_type" not in owner_project.json()
    assert "webhook_url" not in owner_project.json()
    assert "Configured" in owner_page.text
    assert 'name="url"' in owner_page.text
    assert secret not in owner_page.text
    assert client.post(
        disconnect_url,
        data={"confirm": "Disconnect", **_csrf(settings_world.owner)},
        follow_redirects=False,
    ).status_code == 303
    assert chat_webhooks(session, settings_world.project.id) == []


def test_chat_integration_connects_and_rejects_invalid_provider_and_confirmation(
    client, settings_world, session, login_as
):
    base = f"/projects/{settings_world.project.slug}/settings/integrations"
    login_as(settings_world.owner.email)

    connected = client.post(
        f"{base}/TEAMS",
        data={"url": "https://hooks.example.test/teams", **_csrf(settings_world.owner)},
        follow_redirects=False,
    )
    lowercase = client.post(
        f"{base}/teams",
        data={"url": "https://hooks.example.test/teams", **_csrf(settings_world.owner)},
    )
    wrong_confirm = client.post(
        f"{base}/TEAMS/disconnect",
        data={"confirm": "yes", **_csrf(settings_world.owner)},
    )

    assert connected.status_code == 303
    assert [row.provider for row in chat_webhooks(session, settings_world.project.id)] == [
        WebhookType.TEAMS
    ]
    assert lowercase.status_code == 404
    assert wrong_confirm.status_code == 422


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
