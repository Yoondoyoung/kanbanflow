import pytest
from sqlmodel import Session

from app.models import Project
from app.routers.api_projects import slugify


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Payment Gateway", "payment-gateway"),
        ("  Spaced  Out  ", "spaced-out"),
        ("Rock & Roll!!", "rock-roll"),
        ("CS482 — Team 3", "cs482-team-3"),
        ("x" * 80, "x" * 50),
        # Entirely non-alphanumeric input (ASCII punctuation or a non-Latin
        # script) has nothing for the regex to keep, so it collapses to the
        # empty string. The brief specifies the resulting behaviour at the
        # route level (test_unslugifiable_name_returns_422 below): an empty
        # slug is rejected with 422 rather than silently stored or defaulted,
        # since an empty slug would be a value that collides with every other
        # unslugifiable name and produces unreachable URLs.
        ("!!!", ""),
        ("日本語", ""),
        # Truncating to 50 chars can land exactly on a separator hyphen
        # (position 50 here falls on the hyphen from the space at index 49).
        # The trailing .strip("-") after the slice exists specifically to
        # clean that up; without it this would end in "-".
        ("a" * 49 + " " + "b" * 10, "a" * 49),
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected


def test_create_project_makes_the_creator_an_owner(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.post("/api/v1/projects", json={"name": "Payment Gateway"})
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "payment-gateway"
    assert body["role"] == "OWNER"


def test_duplicate_slug_returns_409(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    client.post("/api/v1/projects", json={"name": "Payment Gateway"})
    response = client.post("/api/v1/projects", json={"name": "payment gateway"})
    assert response.status_code == 409
    assert "payment-gateway" in response.text


def test_unslugifiable_name_returns_422(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    assert client.post("/api/v1/projects", json={"name": "!!!"}).status_code == 422


def test_project_list_shows_only_projects_you_belong_to(client, make_user, login_as):
    make_user(email="ada@example.com")
    make_user(email="bob@example.com")
    login_as("ada@example.com")
    client.post("/api/v1/projects", json={"name": "Ada Project"})

    own_projects = client.get("/api/v1/projects").json()
    assert len(own_projects) == 1
    assert own_projects[0]["slug"] == "ada-project"
    assert own_projects[0]["role"] == "OWNER"

    client.post("/api/v1/auth/logout")
    login_as("bob@example.com")
    assert client.get("/api/v1/projects").json() == []


def test_non_member_gets_404_on_project_detail(client, make_user, login_as):
    make_user(email="ada@example.com")
    make_user(email="bob@example.com")
    login_as("ada@example.com")
    client.post("/api/v1/projects", json={"name": "Ada Project"})
    client.post("/api/v1/auth/logout")
    login_as("bob@example.com")
    assert client.get("/api/v1/projects/ada-project").status_code == 404


def test_anonymous_request_is_401(client):
    assert client.post("/api/v1/projects", json={"name": "X"}).status_code == 401


def test_concurrent_project_creation_race_returns_409_not_500(
    client, make_user, login_as, engine, monkeypatch
):
    # Simulate two concurrent POST /api/v1/projects calls deriving the same
    # slug: a "racer" request commits its own row for the slug in the gap
    # between our request's pre-check and its own insert, so our insert hits
    # the real unique constraint on Project.slug and must surface as 409, not
    # an unhandled 500 (Ruling R16). We hook the first session.exec() call a
    # request makes — that's the pre-check's select() — since there's no
    # standalone function analogous to api_auth's hash_password to monkeypatch
    # in this route.
    make_user(email="ada@example.com")
    login_as("ada@example.com")

    original_exec = Session.exec
    state = {"triggered": False}

    # Assumes app.auth.optional_user resolves the logged-in user via
    # session.get(User, user_id) rather than session.exec(select(User)...)
    # (app/auth.py:53) — so the first exec() call this request makes is the
    # route's own slug pre-check, not a lookup from login_as's session cookie.
    # If optional_user ever switches to session.exec(), the racer would fire
    # before the pre-check instead of after it: the pre-check would then see
    # the conflict itself and return its ordinary 409, and this test would
    # keep passing while silently testing the wrong branch (the pre-check,
    # not the except IntegrityError handler).
    def exec_then_insert_racer(self, *args, **kwargs):
        result = original_exec(self, *args, **kwargs)
        if not state["triggered"]:
            state["triggered"] = True
            with Session(engine) as racer_session:
                racer_session.add(Project(name="Racer", slug="payment-gateway"))
                racer_session.commit()
        return result

    monkeypatch.setattr(Session, "exec", exec_then_insert_racer)

    response = client.post("/api/v1/projects", json={"name": "Payment Gateway"})
    assert response.status_code == 409
    assert "payment-gateway" in response.text
