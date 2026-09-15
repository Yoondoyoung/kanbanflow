import os
import subprocess

from sqlalchemy import inspect
from sqlmodel import SQLModel

from app import models  # noqa: F401  — imported for its side effect of registering tables
from app.db import make_engine


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
