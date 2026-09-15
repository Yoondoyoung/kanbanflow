import pytest


@pytest.fixture
def seeded(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    for i in range(5):
        client.post(
            "/api/v1/tickets",
            json={
                "slug": project.slug,
                "title": f"Ticket {i}",
                "priority": "HIGH" if i % 2 else "LOW",
                "type": "BUG" if i % 2 else "STORY",
            },
        )
    return owner, project


def test_board_query_is_newest_first(client, seeded):
    _, project = seeded
    items = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"]
    assert [t["ticket_number"] for t in items] == [5, 4, 3, 2, 1]


def test_board_query_filters(client, seeded):
    _, project = seeded
    items = client.get(
        f"/api/v1/projects/{project.slug}/tickets", params={"priority": "HIGH"}
    ).json()["items"]
    assert {t["priority"] for t in items} == {"HIGH"}
    items = client.get(f"/api/v1/projects/{project.slug}/tickets", params={"type": "BUG"}).json()[
        "items"
    ]
    assert {t["type"] for t in items} == {"BUG"}


def test_board_query_paginates(client, seeded):
    _, project = seeded
    first = client.get(f"/api/v1/projects/{project.slug}/tickets", params={"limit": 2}).json()
    assert [t["ticket_number"] for t in first["items"]] == [5, 4]
    assert first["next_cursor"] == 4
    second = client.get(
        f"/api/v1/projects/{project.slug}/tickets", params={"limit": 2, "cursor": 4}
    ).json()
    assert [t["ticket_number"] for t in second["items"]] == [3, 2]


def test_board_query_pagination_terminal_page(client, seeded):
    _, project = seeded
    third = client.get(
        f"/api/v1/projects/{project.slug}/tickets", params={"limit": 2, "cursor": 2}
    ).json()
    assert [t["ticket_number"] for t in third["items"]] == [1]
    assert third["next_cursor"] is None

    empty = client.get(
        f"/api/v1/projects/{project.slug}/tickets", params={"limit": 2, "cursor": 1}
    ).json()
    assert empty["items"] == []
    assert empty["next_cursor"] is None


def test_limit_above_200_is_rejected(client, seeded):
    _, project = seeded
    assert (
        client.get(f"/api/v1/projects/{project.slug}/tickets", params={"limit": 201}).status_code
        == 422
    )


def test_board_query_rejects_invalid_status(client, seeded):
    _, project = seeded
    assert (
        client.get(
            f"/api/v1/projects/{project.slug}/tickets", params={"status": "NOT_A_REAL_STATUS"}
        ).status_code
        == 422
    )


def test_patch_updates_fields_and_rejects_bad_meta(client, seeded):
    _, project = seeded
    ticket_id = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]["id"]
    response = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"title": "Renamed", "story_points": 8, "meta": {"git_commit": "abc1234"}},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert response.json()["story_points"] == 8
    assert (
        client.patch(
            f"/api/v1/tickets/{ticket_id}", json={"meta": {"blob": "x" * 9000}}
        ).status_code
        == 422
    )


def test_patch_empty_body_leaves_ticket_unchanged(client, seeded):
    _, project = seeded
    ticket = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]
    response = client.patch(f"/api/v1/tickets/{ticket['id']}", json={})
    assert response.status_code == 200
    assert response.json() == ticket


def test_get_ticket_returns_ticket(client, seeded):
    _, project = seeded
    item = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]
    response = client.get(f"/api/v1/tickets/{item['id']}")
    assert response.status_code == 200
    assert response.json() == item


def test_non_member_gets_404_on_ticket_read(client, seeded, make_user, login_as):
    _, project = seeded
    ticket_id = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]["id"]
    make_user(email="bob@example.com")
    client.post("/api/v1/auth/logout")
    login_as("bob@example.com")
    assert client.get(f"/api/v1/tickets/{ticket_id}").status_code == 404


def test_only_owner_deletes(client, seeded, make_user, add_member, login_as):
    _, project = seeded
    ticket_id = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]["id"]
    bob = make_user(email="bob@example.com")
    add_member(project, bob)
    client.post("/api/v1/auth/logout")
    login_as("bob@example.com")
    assert client.delete(f"/api/v1/tickets/{ticket_id}").status_code == 403
    client.post("/api/v1/auth/logout")
    login_as("ada@example.com")
    assert client.delete(f"/api/v1/tickets/{ticket_id}").status_code == 204


@pytest.mark.parametrize("field", ["title", "description", "type", "priority", "meta"])
def test_patch_rejects_explicit_null_on_non_nullable_field(client, seeded, field):
    # Every TicketUpdate field is `| None`, so exclude_unset keeps an explicit
    # JSON null. Without the guard in patch_ticket these reach setattr and the
    # NOT NULL column blows up as an unhandled IntegrityError (500).
    _, project = seeded
    before = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]
    response = client.patch(f"/api/v1/tickets/{before['id']}", json={field: None})
    assert response.status_code == 422
    assert response.json()["detail"] == f"{field} may not be null"
    assert client.get(f"/api/v1/tickets/{before['id']}").json() == before


def test_patch_null_meta_does_not_poison_the_project_ticket_list(client, seeded):
    # meta is Column(JSON, nullable=False): a JSON null serialises to the
    # literal string 'null', satisfies NOT NULL, and *persists* -- after which
    # every member's GET of the project's ticket list fails response validation.
    _, project = seeded
    ticket_id = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]["id"]
    assert client.patch(f"/api/v1/tickets/{ticket_id}", json={"meta": None}).status_code == 422
    listing = client.get(f"/api/v1/projects/{project.slug}/tickets")
    assert listing.status_code == 200
    assert all(t["meta"] == {} for t in listing.json()["items"])


def test_patch_accepts_null_on_the_nullable_fields(client, seeded):
    _, project = seeded
    ticket_id = client.get(f"/api/v1/projects/{project.slug}/tickets").json()["items"][0]["id"]
    client.patch(f"/api/v1/tickets/{ticket_id}", json={"story_points": 8})
    response = client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"story_points": None, "assignee_id": None, "resolution_notes": None},
    )
    assert response.status_code == 200
    assert response.json()["story_points"] is None
