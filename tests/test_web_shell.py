from pathlib import Path


def test_signed_in_shell_has_project_sidebar(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as(owner.email)

    page = client.get("/dashboard")

    assert 'data-testid="app-sidebar"' in page.text
    assert f'href="/projects/{project.slug}"' in page.text
    assert 'href="/static/app.css"' in page.text
    assert 'href="#main-content">Skip to main content</a>' in page.text


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


def test_dialogs_have_names_escape_handling_and_focus_targets():
    dashboard = Path("app/templates/dashboard.html").read_text()
    board = Path("app/templates/board.html").read_text()
    backlog = Path("app/templates/backlog.html").read_text()
    ticket_modal = Path("app/templates/partials/ticket_modal.html").read_text()
    close_dialog = Path("app/templates/partials/sprint_close.html").read_text()

    assert 'role="dialog" aria-modal="true" aria-labelledby="project-dialog-heading"' in dashboard
    assert "$refs.projectName.focus()" in dashboard
    assert "$refs.projectDialogOpener.focus()" in dashboard
    assert '<dialog id="ticket-modal"' in ticket_modal
    assert 'role="dialog" aria-modal="true" aria-labelledby="ticket-modal-heading"' in ticket_modal
    assert "x-data=" not in ticket_modal
    assert '@cancel="$event.preventDefault(); $el.close()"' in ticket_modal
    assert 'x-ref="ticketTitle"' in ticket_modal
    assert "$refs.ticketModalOpener.focus()" in ticket_modal
    for page in (board, backlog):
        assert "x-data=\"{ ticketError: '' }\"" in page
        assert 'x-ref="ticketModalOpener"' in page
        assert "$refs.ticketModal.showModal()" in page
        assert "$refs.ticketTitle.focus()" in page
    assert "@htmx:after-request.camel=" in ticket_modal
    assert "$event.detail.xhr.status >= 200 && $event.detail.xhr.status < 300" in ticket_modal
    assert "$event.detail.successful" not in ticket_modal
    assert "ticketError = $event.detail.xhr.responseText" in ticket_modal
    assert "ticketError = ''; $el.reset()" in ticket_modal
    assert '@cancel="$event.preventDefault(); $el.close()"' in close_dialog
    assert "$el.querySelector('h2').focus()" in close_dialog
    assert "$refs.closeFormOpener.focus()" in close_dialog


def test_styles_respect_reduced_motion():
    stylesheet = Path("app/static/app.css").read_text()

    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert "transition-duration: 0.01ms !important" in stylesheet
