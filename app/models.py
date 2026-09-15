import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Role(StrEnum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"


class WebhookType(StrEnum):
    NONE = "NONE"
    TEAMS = "TEAMS"
    SLACK = "SLACK"
    DISCORD = "DISCORD"


class TicketType(StrEnum):
    STORY = "STORY"
    BUG = "BUG"
    DEMO_REQUEST = "DEMO_REQUEST"
    TASK = "TASK"


class TicketStatus(StrEnum):
    BACKLOG = "BACKLOG"
    SELECTED = "SELECTED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(max_length=50)
    email: str = Field(max_length=255, unique=True, index=True)
    password_hash: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=utcnow)


class Project(SQLModel, table=True):
    __tablename__ = "project"

    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(max_length=100)
    slug: str = Field(max_length=50, unique=True, index=True)
    webhook_type: WebhookType = Field(default=WebhookType.NONE)
    webhook_url: str | None = Field(default=None, max_length=500)
    next_ticket_number: int = Field(default=1)
    created_at: datetime = Field(default_factory=utcnow)


class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_member"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_member_project_user"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    role: Role = Field(default=Role.MEMBER)
    joined_at: datetime = Field(default_factory=utcnow)


class Ticket(SQLModel, table=True):
    __tablename__ = "ticket"
    __table_args__ = (
        UniqueConstraint("project_id", "ticket_number", name="uq_ticket_project_number"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    ticket_number: int = Field(index=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str = Field(max_length=255)
    description: str = Field(default="", max_length=20000)
    type: TicketType = Field(default=TicketType.TASK)
    status: TicketStatus = Field(default=TicketStatus.BACKLOG, index=True)
    priority: Priority = Field(default=Priority.MEDIUM)
    story_points: int | None = Field(default=None)
    creator_id: str = Field(foreign_key="user.id")
    assignee_id: str | None = Field(default=None, foreign_key="user.id", index=True)
    resolution_notes: str | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    meta: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
