from app.auth import SESSION_COOKIE
from app.main import templates


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "<form" in response.text


def test_register_form_creates_a_session_and_redirects(client):
    response = client.post(
        "/register",
        data={"name": "Ada", "email": "ada@example.com", "password": "hunter22"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert SESSION_COOKIE in response.cookies


def test_duplicate_registration_rerenders_with_an_error(client, make_user):
    make_user(email="ada@example.com")
    response = client.post(
        "/register",
        data={"name": "Ada", "email": "ada@example.com", "password": "hunter22"},
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "already registered" in response.text.lower()


def test_bad_login_rerenders_with_an_error(client, make_user):
    make_user(email="ada@example.com")
    response = client.post(
        "/login", data={"email": "ada@example.com", "password": "wrong"}, follow_redirects=False
    )
    assert response.status_code == 401
    assert "invalid" in response.text.lower()


def test_overlong_password_rerenders_with_an_error_instead_of_crashing(client):
    # bcrypt (via hash_password) raises ValueError past 72 UTF-8 bytes. The JSON route is
    # protected by RegisterRequest's validator; this form-based route has no schema in front
    # of it, so it needs its own guard or an over-length password would 500 instead of 422.
    response = client.post(
        "/register",
        data={"name": "Ada", "email": "ada@example.com", "password": "a" * 73},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "72 bytes" in response.text


def test_root_redirects_anonymous_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_logged_in_user_visiting_login_is_redirected_to_dashboard(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_logged_in_user_visiting_register_is_redirected_to_dashboard(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    response = client.get("/register", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_logout_clears_the_session_cookie(client, make_user, login_as):
    make_user(email="ada@example.com")
    login_as("ada@example.com")
    assert client.cookies.get(SESSION_COOKIE) is not None

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    # httpx's cookie jar drops a cookie whose Set-Cookie response has already expired.
    assert client.cookies.get(SESSION_COOKIE) is None


def test_markdown_filter_is_registered_on_the_templates_environment_and_renders():
    # A dict-membership check ("markdown" in templates.env.filters) would pass even if the
    # filter were registered on a different Environment than the one TemplateResponse actually
    # uses. Rendering through templates.env itself proves it reaches real template output.
    # autoescape is on, so | safe is required after | markdown -- exactly how a real
    # template would use it (e.g. `{{ ticket.description | markdown | safe }}`).
    rendered = templates.env.from_string("{{ '**bold**' | markdown | safe }}").render()
    assert "<strong>bold</strong>" in rendered
