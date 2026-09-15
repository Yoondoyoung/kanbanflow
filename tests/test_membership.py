from sqlmodel import Session

from app.models import ProjectMember, Role


def test_owner_adds_member_by_email(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    make_user(email="bob@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.post(
        f"/api/v1/projects/{project.slug}/members",
        json={"email": "bob@example.com", "role": "MEMBER"},
    )
    assert response.status_code == 201
    assert response.json()["email"] == "bob@example.com"


def test_adding_unknown_email_is_404_and_duplicate_is_409(
    client, make_user, make_project, login_as
):
    owner = make_user(email="ada@example.com")
    make_user(email="bob@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    assert (
        client.post(
            f"/api/v1/projects/{project.slug}/members",
            json={"email": "ghost@example.com", "role": "MEMBER"},
        ).status_code
        == 404
    )
    body = {"email": "bob@example.com", "role": "MEMBER"}
    client.post(f"/api/v1/projects/{project.slug}/members", json=body)
    assert client.post(f"/api/v1/projects/{project.slug}/members", json=body).status_code == 409


def test_member_cannot_manage_membership(client, make_user, make_project, add_member, login_as):
    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    add_member(project, bob)
    login_as("bob@example.com")
    assert client.get(f"/api/v1/projects/{project.slug}/members").status_code == 200
    assert (
        client.post(
            f"/api/v1/projects/{project.slug}/members",
            json={"email": "ada@example.com", "role": "MEMBER"},
        ).status_code
        == 403
    )


def test_last_owner_cannot_be_demoted_or_removed(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    assert (
        client.patch(
            f"/api/v1/projects/{project.slug}/members/{owner.id}", json={"role": "MEMBER"}
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/projects/{project.slug}/members/{owner.id}").status_code == 409


def test_removing_a_member_nulls_their_assigned_tickets(
    client, make_user, make_project, add_member, login_as, session
):
    from app.models import Ticket, TicketType

    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    add_member(project, bob)
    ticket = Ticket(
        ticket_number=1,
        project_id=project.id,
        title="t",
        type=TicketType.TASK,
        creator_id=owner.id,
        assignee_id=bob.id,
    )
    session.add(ticket)
    session.commit()
    login_as("ada@example.com")
    assert client.delete(f"/api/v1/projects/{project.slug}/members/{bob.id}").status_code == 204
    session.expire_all()
    assert session.get(Ticket, ticket.id).assignee_id is None


def test_second_owner_can_be_demoted_then_removed(
    client, make_user, make_project, add_member, login_as
):
    # With two owners, neither guard should fire: demoting one still leaves
    # one OWNER, and removing that now-MEMBER user leaves the project intact.
    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    add_member(project, bob, role=Role.OWNER)
    login_as("ada@example.com")
    response = client.patch(
        f"/api/v1/projects/{project.slug}/members/{bob.id}", json={"role": "MEMBER"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "MEMBER"
    assert client.delete(f"/api/v1/projects/{project.slug}/members/{bob.id}").status_code == 204


def test_list_members_returns_every_member_not_just_caller(
    client, make_user, make_project, add_member, login_as
):
    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    add_member(project, bob)
    login_as("bob@example.com")
    response = client.get(f"/api/v1/projects/{project.slug}/members")
    assert response.status_code == 200
    emails = {m["email"] for m in response.json()}
    assert emails == {"ada@example.com", "bob@example.com"}


def test_concurrent_member_add_race_returns_409_not_500(
    client, make_user, make_project, login_as, engine, monkeypatch
):
    # Same shape as test_concurrent_project_creation_race_returns_409_not_500
    # and test_concurrent_registration_race_returns_409_not_500 (Ruling R16):
    # two concurrent adds of the same user both pass the pre-check, and the
    # second commit must hit ProjectMember's unique constraint and surface as
    # 409, not an unhandled 500.
    owner = make_user(email="ada@example.com")
    bob = make_user(email="bob@example.com")
    project = make_project(owner)
    login_as("ada@example.com")

    original_exec = Session.exec
    state = {"triggered": False}

    def exec_then_insert_racer(self, *args, **kwargs):
        result = original_exec(self, *args, **kwargs)
        if not state["triggered"]:
            state["triggered"] = True
            with Session(engine) as racer_session:
                racer_session.add(
                    ProjectMember(project_id=project.id, user_id=bob.id, role=Role.MEMBER)
                )
                racer_session.commit()
        return result

    monkeypatch.setattr(Session, "exec", exec_then_insert_racer)

    response = client.post(
        f"/api/v1/projects/{project.slug}/members",
        json={"email": "bob@example.com", "role": "MEMBER"},
    )
    assert response.status_code == 409
