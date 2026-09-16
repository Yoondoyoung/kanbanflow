from sqlmodel import Session

from app.models import Ticket, TicketStatus, TicketType


def test_board_renders_four_fixed_columns(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    page = client.get(f"/projects/{project.slug}").text
    for column in ["BACKLOG", "SELECTED", "IN_PROGRESS", "DONE"]:
        assert f'id="column-{column}"' in page


def test_board_shows_tickets_in_their_columns(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    created = client.post(
        "/api/v1/tickets", json={"slug": project.slug, "title": "Card declines"}
    ).json()
    client.patch(f"/api/v1/tickets/{created['id']}/status", json={"status": "IN_PROGRESS"})
    page = client.get(f"/projects/{project.slug}").text
    assert "Card declines" in page
    assert f'id="ticket-{created["id"]}"' in page


def test_board_renders_markdown_descriptions_inertly(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    client.post(
        "/api/v1/tickets",
        json={
            "slug": project.slug,
            "title": "XSS attempt",
            "description": "<script>alert('xss')</script> and <img src=x onerror=\"alert(1)\">",
        },
    )
    page = client.get(f"/projects/{project.slug}").text
    # V-9's actual pass condition (Ruling 3): no *live* <script> or <img> tag reaches
    # the page. render_markdown (Task 18) escapes the raw HTML to inert text rather
    # than deleting it -- so the literal word "onerror" still appears, harmlessly,
    # inside an entity-escaped string. Asserting that substring's absence would
    # contradict Task 18's own established behavior (tests/test_rendering.py::
    # test_img_onerror_in_source_is_neutralized). Check for live tags instead.
    assert "<script>" not in page
    assert "<img" not in page
    assert "alert" in page


def test_non_member_gets_404_for_the_board(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    make_user(email="bob@example.com")
    project = make_project(owner)
    login_as("bob@example.com")
    assert client.get(f"/projects/{project.slug}").status_code == 404


def test_anonymous_visitor_is_redirected(client, make_user, make_project):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    response = client.get(f"/projects/{project.slug}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_empty_project_renders_four_empty_columns(client, make_user, make_project, login_as):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    login_as("ada@example.com")
    response = client.get(f"/projects/{project.slug}")
    assert response.status_code == 200
    for column in ["BACKLOG", "SELECTED", "IN_PROGRESS", "DONE"]:
        assert f'id="column-{column}"' in response.text


def test_board_caps_each_column_and_shows_a_truncation_notice(
    client, engine, make_user, make_project, login_as
):
    owner = make_user(email="ada@example.com")
    project = make_project(owner)
    with Session(engine) as session:
        session.add_all(
            [
                Ticket(
                    ticket_number=n,
                    project_id=project.id,
                    title=f"Ticket {n}",
                    type=TicketType.TASK,
                    status=TicketStatus.BACKLOG,
                    creator_id=owner.id,
                )
                for n in range(1, 202)
            ]
        )
        session.commit()
    login_as("ada@example.com")

    page = client.get(f"/projects/{project.slug}").text

    assert page.count('<article id="ticket-') == 200
    assert "Showing the first 200 tickets." in page


def test_ticket_card_partial_renders_standalone():
    from fastapi.templating import Jinja2Templates

    from app.models import Priority, Ticket, TicketStatus, TicketType
    from app.rendering import render_markdown

    templates = Jinja2Templates(directory="app/templates")
    templates.env.filters["markdown"] = render_markdown

    class FakeProject:
        slug = "payment-gateway"

    ticket = Ticket(
        ticket_number=1,
        project_id="proj-1",
        title="Card declines",
        description="**bold**",
        type=TicketType.BUG,
        status=TicketStatus.BACKLOG,
        priority=Priority.HIGH,
        creator_id="user-1",
    )
    html = templates.get_template("partials/ticket_card.html").render(
        ticket=ticket,
        project=FakeProject(),
        columns=[
            TicketStatus.BACKLOG,
            TicketStatus.SELECTED,
            TicketStatus.IN_PROGRESS,
            TicketStatus.DONE,
        ],
        csrf_token="tok",
    )
    assert f'id="ticket-{ticket.id}"' in html
    assert "Card declines" in html
    assert "<strong>bold</strong>" in html
