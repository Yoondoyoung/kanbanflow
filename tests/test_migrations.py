import os
import subprocess
from datetime import date

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from app import models  # noqa: F401  — imported for its side effect of registering tables
from app.db import make_engine
from app.models import Sprint, SprintStatus, SprintTicketHistory, Ticket, TicketStatus, User


def test_migration_produces_the_same_tables_as_the_models(tmp_path):
    db = tmp_path / "migrated.db"
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={"DATABASE_URL": f"sqlite:///{db}", "PATH": os.environ["PATH"]},
    )
    inspector = inspect(make_engine(f"sqlite:///{db}"))
    migrated = set(inspector.get_table_names())
    expected = set(SQLModel.metadata.tables) | {"alembic_version"}
    assert expected <= migrated

    # Table names agreeing isn't enough — a dropped or renamed column would still
    # pass that check. Compare each table's actual columns against the model.
    for table_name, table in SQLModel.metadata.tables.items():
        migrated_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in table.columns}
        assert migrated_columns == model_columns, f"{table_name} columns disagree"


def test_api_token_migration_creates_indexes_and_user_foreign_key(tmp_path):
    db = tmp_path / "migrated.db"
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={"DATABASE_URL": f"sqlite:///{db}", "PATH": os.environ["PATH"]},
    )
    inspector = inspect(make_engine(f"sqlite:///{db}"))

    expected_columns = {
        "id",
        "user_id",
        "label",
        "prefix",
        "token_hash",
        "created_at",
        "last_used_at",
        "revoked_at",
    }
    assert expected_columns == {column["name"] for column in inspector.get_columns("api_token")}
    indexes = {index["name"]: index for index in inspector.get_indexes("api_token")}
    assert not indexes["ix_api_token_user_id"]["unique"]
    assert indexes["ix_api_token_token_hash"]["unique"]
    referred_tables = {
        foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("api_token")
    }
    assert referred_tables == {"user"}


def test_api_token_migration_downgrade_and_upgrade_are_safe(tmp_path):
    db = tmp_path / "migrated.db"
    env = {"DATABASE_URL": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env)
    subprocess.run(["uv", "run", "alembic", "downgrade", "-1"], check=True, env=env)

    assert "api_token" not in inspect(make_engine(f"sqlite:///{db}")).get_table_names()

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env)
    assert "api_token" in inspect(make_engine(f"sqlite:///{db}")).get_table_names()


def test_sprint_migration_creates_constraints(tmp_path):
    db = tmp_path / "migrated.db"
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={"DATABASE_URL": f"sqlite:///{db}", "PATH": os.environ["PATH"]},
    )
    inspector = inspect(make_engine(f"sqlite:///{db}"))

    assert {"sprint", "sprint_ticket_history"} <= set(inspector.get_table_names())
    assert {"sprint_id", "first_sprint_entered_at", "delayed_days", "rollover_count"} <= {
        column["name"] for column in inspector.get_columns("ticket")
    }
    assert {"uq_sprint_active_project", "uq_sprint_planning_project"} <= {
        index["name"] for index in inspector.get_indexes("sprint")
    }
    assert {
        foreign_key["referred_table"] for foreign_key in inspector.get_foreign_keys("ticket")
    } >= {"sprint"}


def test_sprint_migration_rejects_invalid_dates(tmp_path):
    db = tmp_path / "migrated.db"
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={"DATABASE_URL": f"sqlite:///{db}", "PATH": os.environ["PATH"]},
    )
    engine = make_engine(f"sqlite:///{db}")

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO project (id, name, slug, webhook_type, next_ticket_number, "
                "created_at) "
                "VALUES ('project-1', 'Project', 'project', 'NONE', 1, CURRENT_TIMESTAMP)"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO sprint (id, project_id, name, goal, status, start_date, end_date) "
                    "VALUES ('sprint-1', 'project-1', 'Sprint 1', 'Impossible', 'PLANNING', "
                    "'2026-09-28', '2026-09-21')"
                )
            )


def test_sprint_migration_enforces_status_and_history_constraints(tmp_path):
    db = tmp_path / "migrated.db"
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        env={"DATABASE_URL": f"sqlite:///{db}", "PATH": os.environ["PATH"]},
    )
    engine = make_engine(f"sqlite:///{db}")

    with Session(engine) as session:
        owner = User(name="Owner", email="owner@example.com", password_hash="x")
        project = models.Project(name="Project", slug="project")
        session.add_all([owner, project])
        session.commit()
        ticket = Ticket(ticket_number=1, project_id=project.id, title="Ticket", creator_id=owner.id)
        session.add(ticket)
        session.commit()

        sprint_kwargs = {
            "project_id": project.id,
            "goal": "Goal",
            "start_date": date(2026, 9, 21),
            "end_date": date(2026, 9, 28),
        }
        planning = Sprint(name="Planning", status=SprintStatus.PLANNING, **sprint_kwargs)
        session.add(planning)
        session.commit()
        session.add(Sprint(name="Planning 2", status=SprintStatus.PLANNING, **sprint_kwargs))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        active = Sprint(name="Active", status=SprintStatus.ACTIVE, **sprint_kwargs)
        session.add(active)
        session.commit()
        session.add(Sprint(name="Active 2", status=SprintStatus.ACTIVE, **sprint_kwargs))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add_all(
            [
                Sprint(name="Closed 1", status=SprintStatus.CLOSED, **sprint_kwargs),
                Sprint(name="Closed 2", status=SprintStatus.CLOSED, **sprint_kwargs),
            ]
        )
        session.commit()

        session.add(
            SprintTicketHistory(
                sprint_id=planning.id,
                ticket_id=ticket.id,
                status_at_close=TicketStatus.DONE,
                was_completed=True,
            )
        )
        session.commit()
        session.add(
            SprintTicketHistory(
                sprint_id=planning.id,
                ticket_id=ticket.id,
                status_at_close=TicketStatus.BACKLOG,
                was_completed=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
