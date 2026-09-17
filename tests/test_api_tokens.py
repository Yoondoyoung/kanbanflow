import hashlib
from datetime import timedelta

from sqlmodel import select

from app.models import ApiToken, utcnow


def issue_token(client, login_as, email="ada@example.com"):
    login_as(email)
    response = client.post("/api/v1/tokens", json={"label": "Cursor"})
    assert response.status_code == 201, response.text
    return response.json()


def test_issuing_token_returns_plaintext_once_and_stores_only_its_hash(
    client, session, make_user, login_as
):
    make_user(email="ada@example.com")

    issued = issue_token(client, login_as)

    assert issued["token"].startswith("kf_")
    stored = session.exec(select(ApiToken)).one()
    assert stored.token_hash == hashlib.sha256(issued["token"].encode()).hexdigest()
    assert stored.token_hash != issued["token"]
    assert issued["prefix"] == issued["token"][:10]

    listed = client.get("/api/v1/tokens")
    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": issued["id"],
            "label": "Cursor",
            "prefix": issued["prefix"],
            "created_at": issued["created_at"],
            "last_used_at": None,
            "revoked_at": None,
        }
    ]


def test_issued_token_authenticates_after_cookie_logout(client, make_user, login_as):
    make_user(email="ada@example.com")
    issued = issue_token(client, login_as)
    client.post("/api/v1/auth/logout")

    response = client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {issued['token']}"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_invalid_bearer_does_not_fall_back_to_a_valid_cookie(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")

    response = client.get("/api/v1/projects", headers={"Authorization": "Bearer unknown"})

    assert response.status_code == 401


def test_malformed_authorization_does_not_fall_back_to_a_valid_cookie(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")

    response = client.get("/api/v1/projects", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401


def test_revoking_token_is_idempotent_and_prevents_bearer_authentication(
    client, make_user, login_as
):
    make_user(email="ada@example.com")
    issued = issue_token(client, login_as)

    assert client.delete(f"/api/v1/tokens/{issued['id']}").status_code == 204
    assert client.delete(f"/api/v1/tokens/{issued['id']}").status_code == 204
    client.post("/api/v1/auth/logout")

    response = client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {issued['token']}"}
    )
    assert response.status_code == 401


def test_token_delete_does_not_reveal_or_revoke_another_users_token(client, make_user, login_as):
    make_user(email="ada@example.com")
    ada_token = issue_token(client, login_as)
    client.post("/api/v1/auth/logout")
    make_user(email="bob@example.com")
    login_as("bob@example.com")

    assert client.delete(f"/api/v1/tokens/{ada_token['id']}").status_code == 204
    assert client.get("/api/v1/tokens").json() == []
    client.post("/api/v1/auth/logout")

    response = client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {ada_token['token']}"}
    )
    assert response.status_code == 200


def test_bearer_usage_updates_once_after_an_hour(client, session, make_user, login_as):
    make_user(email="ada@example.com")
    issued = issue_token(client, login_as)
    token = session.exec(select(ApiToken).where(ApiToken.id == issued["id"])).one()
    token.last_used_at = utcnow() - timedelta(hours=2)
    session.commit()
    client.post("/api/v1/auth/logout")

    headers = {"Authorization": f"bearer   {issued['token']}"}
    assert client.get("/api/v1/projects", headers=headers).status_code == 200
    session.refresh(token)
    first_used_at = token.last_used_at
    assert first_used_at is not None

    assert client.get("/api/v1/projects", headers=headers).status_code == 200
    session.refresh(token)
    assert token.last_used_at == first_used_at
