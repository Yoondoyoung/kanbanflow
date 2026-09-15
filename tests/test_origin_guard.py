def test_same_origin_write_is_allowed(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        "/api/v1/tickets",
        json={"slug": project.slug, "title": "T"},
        headers={"Origin": "http://localhost:8000"},
    )
    assert response.status_code == 201


def test_foreign_origin_write_is_rejected(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        "/api/v1/tickets",
        json={"slug": project.slug, "title": "T"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403


def test_missing_origin_is_allowed(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post("/api/v1/tickets", json={"slug": project.slug, "title": "T"})
    assert response.status_code == 201


def test_reads_are_not_blocked_by_origin(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.get(
        f"/api/v1/projects/{project.slug}", headers={"Origin": "https://evil.example.com"}
    )
    assert response.status_code == 200


def test_foreign_origin_write_creates_no_ticket(client, session, make_user, make_project, login_as):
    from sqlmodel import select

    from app.models import Ticket

    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        "/api/v1/tickets",
        json={"slug": project.slug, "title": "T"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert response.status_code == 403
    assert session.exec(select(Ticket)).first() is None
