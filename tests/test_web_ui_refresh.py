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


def test_backlog_has_one_primary_owner_action_without_a_planning_sprint(
    client, make_user, make_project, login_as
):
    """Making both top-level backlog actions primary must make this fail."""
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    page = client.get(f"/projects/{project.slug}/backlog")
    header = re.search(r'<header class="project-header">.*?</header>', page.text, re.DOTALL).group()

    assert 'class="app-secondary-button" type="button" x-ref="ticketModalOpener"' in header
    assert 'class="app-primary-button" type="button" x-ref="sprintFormOpener"' in header


def test_ticket_detail_partial_is_an_accessible_overlay_drawer():
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory="app/templates")
    source = templates.get_template("partials/ticket_detail.html").render(
        ticket=type("Ticket", (), {"ticket_number": 1})(),
        project=type("Project", (), {"slug": "project"})(),
        form_values={
            "title": "Ticket",
            "description": "",
            "type": "TASK",
            "priority": "MEDIUM",
            "story_points": "",
            "assignee_id": "",
            "status": "BACKLOG",
            "sprint_id": "",
            "resolution_notes": "",
        },
        ticket_types=[], priorities=[], columns=[], members=[], sprints=[], csrf_token="token", error=None,
        detail_drawer=True,
    )

    assert '<dialog id="ticket-detail-panel" class="app-dialog ticket-detail-drawer"' in source
    assert "$el.showModal()" in source
    assert "ticket-drawer-closed" in source


def test_remaining_workspace_views_collapse_to_one_column_on_mobile(client):
    css = client.get("/static/app.css")

    assert css.status_code == 200
    mobile_css = css.text.split("@media (max-width: 767px)", 1)[1]
    assert ".sprint-history-row" in mobile_css
    assert ".settings-member" in mobile_css
    assert ".auth-card" in mobile_css
