from collections.abc import Callable

from app.models import Project, Ticket, WebhookType

EVENT_TICKET_CREATED = "TICKET_CREATED"
EVENT_TICKET_DONE = "TICKET_DONE"

_HEADLINES = {
    EVENT_TICKET_CREATED: "New ticket",
    EVENT_TICKET_DONE: "Ticket completed",
}

_UNASSIGNED = "Unassigned"


def build_payload(project: Project, event: str, ticket: Ticket) -> dict:
    return {
        "event": event,
        "project_id": project.id,
        "project_name": project.name,
        "project_slug": project.slug,
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "status": ticket.status.value,
        "type": ticket.type.value,
        "priority": ticket.priority.value,
        "assignee_id": ticket.assignee_id,
    }


def _headline(payload: dict) -> str:
    return (
        f"{_HEADLINES.get(payload['event'], payload['event'])} "
        f"#{payload['ticket_number']}: {payload['title']}"
    )


def _detail(payload: dict) -> str:
    assignee = payload["assignee_id"] or _UNASSIGNED
    return (
        f"{payload['project_name']} · {payload['type']} · "
        f"{payload['priority']} · {payload['status']} · {assignee}"
    )


def format_slack(payload: dict) -> dict:
    return {
        "text": _headline(payload),
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*{_headline(payload)}*"}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": _detail(payload)}]},
        ],
    }


def format_discord(payload: dict) -> dict:
    return {
        "embeds": [
            {
                "title": f"#{payload['ticket_number']} {payload['title']}",
                "description": _detail(payload),
            }
        ]
    }


def format_teams(payload: dict) -> dict:
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": _headline(payload), "weight": "Bolder"},
                        {"type": "TextBlock", "text": _detail(payload), "isSubtle": True},
                    ],
                },
            }
        ],
    }


FORMATTERS: dict[WebhookType, Callable[[dict], dict]] = {
    WebhookType.SLACK: format_slack,
    WebhookType.DISCORD: format_discord,
    WebhookType.TEAMS: format_teams,
}
