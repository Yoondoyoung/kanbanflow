import re

from app.auth import make_csrf_token


def csrf_for(user):
    return make_csrf_token(user.id)


def test_dashboard_lists_projects(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner, name="Payment Gateway")
    login_as("ada@example.com")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Payment Gateway" in response.text
    assert len(re.findall(r"<h1[^>]*>\s*Projects\s*</h1>", response.text)) == 1
    assert 'data-testid="project-row"' in response.text
    assert f'href="/projects/{project.slug}"' in response.text
    assert "OWNER" in response.text


def test_dashboard_has_accessible_project_creation_dialog(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as(owner.email)

    page = client.get("/dashboard")

    assert "New project" in page.text
    assert 'data-testid="project-dialog"' in page.text
    assert 'role="dialog"' in page.text
    assert 'aria-modal="true"' in page.text
    assert 'aria-labelledby="project-dialog-heading"' in page.text


def test_project_dialog_uses_native_focus_management(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as(owner.email)

    page = client.get("/dashboard")

    assert '<dialog id="project-dialog"' in page.text
    assert 'x-ref="project-dialog-opener"' in page.text
    assert 'x-ref="project-dialog"' in page.text
    assert 'x-ref="project-name"' in page.text
    assert "$refs.projectDialog.showModal()" in page.text
    assert "$refs.projectName.focus()" in page.text
    assert '@close="projectDialog = false; $refs.projectDialogOpener.focus()"' in page.text


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_create_project_from_the_form(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.post(
        "/projects",
        data={"name": "Payment Gateway", "_csrf": csrf_for(owner)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/projects/payment-gateway"


def test_create_project_without_csrf_is_403(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.post("/projects", data={"name": "X"}, follow_redirects=False)
    assert response.status_code == 403


def test_create_project_with_another_users_csrf_is_403(client, make_user, login_as):
    make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    login_as("ada@example.com")
    response = client.post(
        "/projects", data={"name": "X", "_csrf": csrf_for(bob)}, follow_redirects=False
    )
    assert response.status_code == 403


def test_rendered_form_contains_a_usable_csrf_token(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    page = client.get("/dashboard").text
    token = re.search(r'name="_csrf" value="([^"]+)"', page).group(1)
    response = client.post(
        "/projects", data={"name": "From Page", "_csrf": token}, follow_redirects=False
    )
    assert response.status_code == 303


# --- Ruling 4: prove verify_csrf is actually wired up, not just returning 403 by
# coincidence -- a missing/tampered token must not leave a project behind. ---


def test_missing_csrf_token_does_not_create_the_project(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    client.post("/projects", data={"name": "X"}, follow_redirects=False)
    assert client.get("/api/v1/projects").json() == []


def test_tampered_csrf_token_does_not_create_the_project(client, make_user, login_as):
    make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    login_as("ada@example.com")
    client.post("/projects", data={"name": "X", "_csrf": csrf_for(bob)}, follow_redirects=False)
    assert client.get("/api/v1/projects").json() == []


# --- Ruling R36: the form route bypasses ProjectCreate entirely, so the name
# limits it enforces (<=100 chars, non-blank after stripping) must be enforced
# on this path too, and proven not to persist an invalid project. ---


def test_overlong_project_name_is_rejected_and_not_persisted(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.post(
        "/projects",
        data={"name": "x" * 101, "_csrf": csrf_for(owner)},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "100" in response.text
    assert 'x-data="{ projectDialog: true }"' in response.text
    assert client.get("/api/v1/projects").json() == []


def test_invalid_project_name_is_escaped_and_preserved_in_the_reopened_dialog(
    client, make_user, login_as
):
    owner = make_user(email="ada@example.com")
    submitted_name = "<project>" * 15
    escaped_name = "&lt;project&gt;" * 15
    login_as(owner.email)

    response = client.post(
        "/projects",
        data={"name": submitted_name, "_csrf": csrf_for(owner)},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert f'value="{escaped_name}"' in response.text
    assert submitted_name not in response.text
    assert 'x-data="{ projectDialog: true }"' in response.text


def test_whitespace_only_project_name_is_rejected_and_not_persisted(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.post(
        "/projects",
        data={"name": "   ", "_csrf": csrf_for(owner)},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert client.get("/api/v1/projects").json() == []


def test_slug_collision_from_the_form_is_a_readable_error_not_a_crash(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as("ada@example.com")
    client.post(
        "/projects",
        data={"name": "Payment Gateway", "_csrf": csrf_for(owner)},
        follow_redirects=False,
    )
    response = client.post(
        "/projects",
        data={"name": "payment gateway", "_csrf": csrf_for(owner)},
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "payment-gateway" in response.text
    # Still on the dashboard, not a bare error body -- the existing project
    # list and the create form both re-render alongside the message.
    assert "<form" in response.text
    assert len(client.get("/api/v1/projects").json()) == 1
