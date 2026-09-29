import asyncio
import logging
import time

import httpx
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import Engine, and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import get_engine
from app.gmail import GmailAuthError, GmailClient, decrypt_token
from app.gmail_parse import parse_message
from app.models import (
    GmailConnection,
    GmailConnectionStatus,
    IntegrationDelivery,
    Priority,
    Project,
    TicketType,
    User,
    utcnow,
)
from app.services import create_ticket

logger = logging.getLogger(__name__)

POLL_SECONDS = 90
_SKIPPED = "Skipped Gmail message"
_access_tokens: dict[str, tuple[str, float]] = {}  # connection id -> (token, monotonic expiry)


def _access_token(connection: GmailConnection, gmail: GmailClient) -> str:
    cached = _access_tokens.get(connection.id)
    if cached and cached[1] > time.monotonic() + 60:
        return cached[0]
    token, expires_in = gmail.access_token(decrypt_token(connection.refresh_token_enc))
    _access_tokens[connection.id] = (token, time.monotonic() + expires_in)
    return token


def _labeled_message_ids(history: list[dict], mapped: set[str]) -> list[str]:
    threads: dict[str, str] = {}  # message id -> thread id
    for record in history:
        for item in (record.get("messagesAdded") or []) + (record.get("labelsAdded") or []):
            message = item.get("message") or {}
            labels = set(item.get("labelIds") or []) | set(message.get("labelIds") or [])
            if message.get("id") and labels & mapped:
                threads[message["id"]] = message.get("threadId") or message["id"]
    # Labeling a conversation labels every message in it; a thread's first message has
    # id == threadId, so importing it first makes the ticket the request, not a reply.
    return sorted(threads, key=lambda message_id: threads[message_id] != message_id)


def _import_message(session: Session, connection: GmailConnection, message: dict) -> str | None:
    """Create a ticket for one message. Returns an error for mail that can never import."""
    label_id = next(
        (label for label in message.get("labelIds") or [] if label in connection.label_mapping),
        None,
    )
    if label_id is None:
        return None  # the label came off before this cycle reached the message
    message_key = f"{connection.project_id}:{message['id']}"
    thread_key = f"{connection.project_id}:{message.get('threadId') or message['id']}"
    seen = session.exec(
        select(IntegrationDelivery.id).where(
            or_(
                and_(
                    IntegrationDelivery.provider == "GMAIL",
                    IntegrationDelivery.delivery_id == message_key,
                ),
                and_(
                    IntegrationDelivery.provider == "GMAIL_THREAD",
                    IntegrationDelivery.delivery_id == thread_key,
                ),
            )
        )
    ).first()
    if seen is not None:
        return None
    try:
        mapping = connection.label_mapping[label_id]
        ticket_type, priority = TicketType(mapping["type"]), Priority(mapping["priority"])
        parsed = parse_message(message)
    except Exception as exc:  # parse_message is pure: any failure is this mail, not Gmail
        return f"{_SKIPPED} {message['id']}: {type(exc).__name__}: {exc}"
    tasks = BackgroundTasks()
    try:
        session.add(
            IntegrationDelivery(provider="GMAIL", delivery_id=message_key, event_type="message")
        )
        session.add(
            IntegrationDelivery(
                provider="GMAIL_THREAD", delivery_id=thread_key, event_type="thread"
            )
        )
        create_ticket(
            session,
            session.get(Project, connection.project_id),
            session.get(User, connection.user_id),
            title=parsed.title,
            description=parsed.description,
            type=ticket_type,
            priority=priority,
            meta={
                "source": "gmail",
                "from": parsed.sender,
                "message_id": message["id"],
                "thread_id": message.get("threadId"),
            },
            tasks=tasks,
        )
    except IntegrityError:
        session.rollback()  # another worker imported this message first
        return None
    except HTTPException as exc:  # ticket validation; a retry would fail the same way
        session.rollback()
        return f"{_SKIPPED} {message['id']}: {exc.detail}"
    for task in tasks.tasks:  # same chat notification as web-created tickets
        task.func(*task.args, **task.kwargs)
    return None


def sync_connection(session: Session, connection: GmailConnection, gmail: GmailClient) -> None:
    """Import newly labeled mail for one connection.

    Transient Gmail or network errors propagate before `history_id` moves, so the next cycle
    replays the batch; delivery rows keep the replay from creating duplicate tickets.
    """
    token = _access_token(connection, gmail)
    try:
        history, latest = gmail.history(token, connection.history_id)
        message_ids = _labeled_message_ids(history, set(connection.label_mapping))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        # Gmail keeps roughly a week of history; past that, rescan recent labeled mail.
        message_ids = list(
            dict.fromkeys(
                message["id"]
                for label_id in connection.label_mapping
                for message in gmail.recent_label_messages(token, label_id)
            )
        )
        latest = str(gmail.profile(token)["historyId"])
    errors = []
    for message_id in message_ids:
        try:
            message = gmail.message(token, message_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            continue  # deleted after the history entry was written; nothing to import
        error = _import_message(session, connection, message)
        if error:
            logger.warning("gmail message skipped: connection_id=%s %s", connection.id, error)
            errors.append(error)
    connection.history_id = latest
    connection.last_synced_at = utcnow()
    if errors:
        connection.last_error = errors[-1][:500]
    elif not (connection.last_error or "").startswith(_SKIPPED):
        connection.last_error = None  # transient errors clear on success; skips stay visible
    session.add(connection)
    session.commit()


def sync_all(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    with Session(engine) as session:
        connection_ids = session.exec(
            select(GmailConnection.id).where(GmailConnection.status == GmailConnectionStatus.ACTIVE)
        ).all()
    if not connection_ids:
        return
    with GmailClient() as gmail:
        for connection_id in connection_ids:
            with Session(engine) as session:
                connection = session.get(GmailConnection, connection_id)
                if connection is None or connection.status != GmailConnectionStatus.ACTIVE:
                    continue
                try:
                    sync_connection(session, connection, gmail)
                except GmailAuthError:
                    session.rollback()
                    _access_tokens.pop(connection_id, None)
                    connection.status = GmailConnectionStatus.NEEDS_REAUTH
                    connection.last_error = "Google access was revoked. Reconnect Gmail."
                    session.add(connection)
                    session.commit()
                    logger.warning("gmail connection needs reauth: connection_id=%s", connection_id)
                except Exception as exc:
                    session.rollback()
                    _access_tokens.pop(connection_id, None)  # a 401 means the cached token died
                    connection.last_error = f"{type(exc).__name__}; retrying next cycle"
                    session.add(connection)
                    session.commit()
                    logger.warning(
                        "gmail sync failed: connection_id=%s", connection_id, exc_info=True
                    )


async def poll_forever() -> None:
    # ponytail: runs inside the single uvicorn worker (Dockerfile `--workers 1`). Extra
    # workers would each poll; delivery rows still block duplicate tickets, but move this to
    # one separate process (or add a lock) before scaling out.
    while True:
        await asyncio.sleep(POLL_SECONDS)
        try:
            await asyncio.to_thread(sync_all)
        except Exception:
            logger.exception("gmail poll cycle failed")
