import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from app.auth import hash_password
from app.db import get_session, make_engine
from app.main import app
from app.models import Project, ProjectMember, Role, User
from app.routers.api_projects import slugify


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(engine):
    def _make(email: str = "user@example.com", password: str = "hunter22", name: str = "User"):
        with Session(engine) as session:
            user = User(name=name, email=email.lower(), password_hash=hash_password(password))
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    return _make


@pytest.fixture
def make_project(engine):
    def _make(owner, name: str = "Payment Gateway"):
        with Session(engine) as session:
            project = Project(name=name, slug=slugify(name))
            session.add(project)
            session.flush()
            session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=Role.OWNER))
            session.commit()
            session.refresh(project)
            return project

    return _make


@pytest.fixture
def login_as(client):
    def _login(email: str, password: str = "hunter22"):
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200, response.text
        return response

    return _login
