import base64


def b64(text: str, charset: str = "utf-8") -> str:
    """Gmail API body encoding: unpadded base64url."""
    return base64.urlsafe_b64encode(text.encode(charset)).decode().rstrip("=")


def gmail_message(
    message_id: str = "msg-1",
    *,
    thread_id: str | None = None,
    labels: tuple[str, ...] = ("Label_1",),
    subject: str = "Need a flyer",
    sender: str = "Jane Doe <jane@example.com>",
    body: str = "Please make a flyer for the fall event.",
    payload: dict | None = None,
) -> dict:
    """A `messages.get(format=full)` resource. Gmail thread ids equal the first message id."""
    return {
        "id": message_id,
        "threadId": thread_id or message_id,
        "labelIds": list(labels),
        "snippet": body[:100],
        "payload": payload
        or {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
            ],
            "body": {"data": b64(body)},
        },
    }
