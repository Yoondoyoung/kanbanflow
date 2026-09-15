from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import WebhookType


def _check_password_byte_length(password: str) -> str:
    # Pydantic's max_length counts characters, not bytes. bcrypt hashes UTF-8
    # bytes and raises an uncaught ValueError past 72 of them, so a multi-byte
    # passphrase (e.g. Korean, 3 bytes/char) can pass the character limit and
    # still crash bcrypt. Catch it here as a 422 instead.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("password must be at most 72 bytes")
    return password


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    _check_password_bytes = field_validator("password")(_check_password_byte_length)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    _check_password_bytes = field_validator("password")(_check_password_byte_length)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    webhook_type: WebhookType | None = None
    webhook_url: str | None = Field(default=None, max_length=500)


class ProjectOut(BaseModel):
    id: str
    name: str
    slug: str
    webhook_type: WebhookType
    webhook_url: str | None
    created_at: datetime
    role: str | None = None
