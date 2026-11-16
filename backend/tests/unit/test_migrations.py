"""Tests for the engine factory and the migration runner's edge cases."""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clipforge.db import MigrationError, init_db, migrate
from sqlalchemy import Engine

Rows = Callable[[str], list[tuple[Any, ...]]]


def _migrations(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(exist_ok=True)
    for name, sql in files.items():
        (directory / name).write_text(sql, encoding="utf-8")
    return directory


def test_engine_uses_clipforge_db_in_configured_data_dir(
    data_dir: Path, rows: Rows
) -> None:
    assert rows("PRAGMA foreign_keys") == [(1,)]
    assert (data_dir / "clipforge.db").is_file()


def test_init_db_migrates_the_database_in_the_given_directory(
    data_dir: Path, tmp_path: Path
) -> None:
    given = tmp_path / "given"
    init_db(given).dispose()
    engine = init_db(given)
    try:
        with engine.connect() as conn:
            versions = conn.exec_driver_sql("SELECT version FROM schema_version").all()
    finally:
        engine.dispose()
    assert [tuple(row) for row in versions] == [(v,) for v in range(1, 41)]
    assert (given / "clipforge.db").is_file()
    assert not data_dir.exists()


def test_migrations_run_in_version_order(
    blank_engine: Engine,
    rows: Rows,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    glob = Path.glob

    def newest_first(self: Path, pattern: str) -> list[Path]:
        """List files newest first; directory order is filesystem-specific."""
        return sorted(glob(self, pattern), reverse=True)

    monkeypatch.setattr(Path, "glob", newest_first)
    directory = _migrations(
        tmp_path / "migrations",
        {
            "010_third.sql": "INSERT INTO log VALUES ('third');",
            "002_second.sql": "INSERT INTO log VALUES ('second');",
            "001_first.sql": "CREATE TABLE log (name TEXT);\n"
            "INSERT INTO log VALUES ('first');",
        },
    )
    assert migrate(blank_engine, directory) == [1, 2, 10]

    _migrations(directory, {"011_fourth.sql": "INSERT INTO log VALUES ('fourth')"})
    assert migrate(blank_engine, directory) == [11]
    names = rows("SELECT name FROM log ORDER BY rowid")
    assert names == [("first",), ("second",), ("third",), ("fourth",)]


def test_failed_migration_is_rolled_back(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    directory = _migrations(
        tmp_path / "migrations",
        {
            "001_ok.sql": "CREATE TABLE a (x INTEGER);",
            "002_bad.sql": "CREATE TABLE b (x INTEGER);\nINSERT INTO a VALUES (1);\n"
            "INSERT INTO missing VALUES (1);",
        },
    )
    with pytest.raises(sqlite3.OperationalError, match="no such table: missing"):
        migrate(blank_engine, directory)

    assert rows("SELECT version FROM schema_version") == [(1,)]
    assert rows("SELECT name FROM sqlite_master WHERE name = 'b'") == []
    assert rows("SELECT count(*) FROM a") == [(0,)]
    assert rows("PRAGMA foreign_keys") == [(1,)]

    _migrations(directory, {"002_bad.sql": "CREATE TABLE b (x INTEGER);"})
    assert migrate(blank_engine, directory) == [2]


def test_migration_leaving_foreign_key_violations_is_rolled_back(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    directory = _migrations(
        tmp_path / "migrations",
        {
            "001_orphan.sql": "CREATE TABLE parent (id INTEGER PRIMARY KEY);\n"
            "CREATE TABLE child (parent_id INTEGER REFERENCES parent (id));\n"
            "INSERT INTO child VALUES (7);",
        },
    )
    with pytest.raises(MigrationError, match="foreign key violations"):
        migrate(blank_engine, directory)

    assert rows("SELECT count(*) FROM schema_version") == [(0,)]
    assert rows("SELECT name FROM sqlite_master") == [("schema_version",)]


@pytest.mark.parametrize(
    "names",
    [["1_init.sql"], ["001-init.sql"], ["001_a.sql", "001_b.sql"]],
)
def test_misnamed_or_duplicate_migrations_are_rejected(
    blank_engine: Engine, rows: Rows, tmp_path: Path, names: list[str]
) -> None:
    directory = _migrations(tmp_path / "migrations", dict.fromkeys(names, "SELECT 1;"))
    with pytest.raises(MigrationError):
        migrate(blank_engine, directory)
    assert rows("SELECT name FROM sqlite_master") == []


def test_missing_migrations_directory_is_rejected(
    blank_engine: Engine, tmp_path: Path
) -> None:
    with pytest.raises(MigrationError, match="not found"):
        migrate(blank_engine, tmp_path / "missing")
