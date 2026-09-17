import re


def test_project_shell_marks_the_open_project(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    page = client.get(f"/projects/{project.slug}/backlog")

    assert page.status_code == 200
    assert f'href="/projects/{project.slug}" class="app-project-link is-active"' in page.text


def test_project_navigation_keeps_settings_as_a_secondary_utility(
    client, make_user, make_project, login_as
):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    page = client.get(f"/projects/{project.slug}/backlog")
    navigation = re.search(
        r'<nav class="project-tabs".*?</nav>', page.text, re.DOTALL
    ).group()

    assert f'/projects/{project.slug}/settings' not in navigation
    assert (
        f'<a class="project-settings-link" href="/projects/{project.slug}/settings">Settings</a>'
        in page.text
    )


def test_sprint_selector_contains_only_sprint_destinations(
    client, make_user, make_project, login_as
):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    page = client.get(f"/projects/{project.slug}/backlog")
    selector = re.search(r'<div class="sprint-selector">.*?</div>', page.text, re.DOTALL).group()

    assert "Backlog" not in selector
    assert "Sprint history" not in selector
    assert "Settings" not in selector
