def test_signed_in_shell_has_project_sidebar(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    page = client.get("/dashboard")

    assert 'data-testid="app-sidebar"' in page.text
    assert f'href="/projects/{project.slug}"' in page.text
    assert 'href="/static/app.css"' in page.text


def test_app_stylesheet_is_served(client):
    response = client.get("/static/app.css")

    assert response.status_code == 200
    assert "--canvas: #f7f7f5" in response.text


def test_mobile_drawer_is_inert_only_while_closed(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as(owner.email)

    page = client.get("/dashboard")

    assert "isMobile: window.matchMedia" in page.text
    assert ':inert="isMobile && !navOpen"' in page.text
    assert ':aria-hidden="(isMobile && !navOpen).toString()"' in page.text
    assert '@keydown.escape.window="navOpen = false"' in page.text
    assert '@click="navOpen = !navOpen"' in page.text


def test_backdrop_hides_and_drawer_closes_when_resized_to_desktop(client, make_user, login_as):
    owner = make_user(email="ada@example.com")
    login_as(owner.email)

    page = client.get("/dashboard")

    assert 'x-show="navOpen && isMobile"' in page.text
    assert "if (!event.matches) navOpen = false" in page.text
