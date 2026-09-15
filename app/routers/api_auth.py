from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from app.auth import (
    DUMMY_HASH,
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    hash_password,
    make_session_cookie,
    verify_password,
)
from app.config import settings
from app.db import get_session
from app.models import User
from app.schemas import LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _set_session(response: Response, user_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        make_session_cookie(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response, session: Session = Depends(get_session)):
    email = body.email.lower()
    if session.exec(select(User).where(User.email == email)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(name=body.name, email=email, password_hash=hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    _set_session(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email.lower())).first()
    hashed = user.password_hash if user else DUMMY_HASH
    if not verify_password(body.password, hashed) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    _set_session(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
