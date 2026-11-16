"""SQLite storage: the engine, the versioned SQL migration runner, and tables.

The schema is defined by migrations/NNN_name.sql files, which migrate() applies
in version order. The SQLModel row classes map those tables; to_model() turns
a row into the matching Pydantic model from clipforge.models.
"""

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import Dialect, Engine, Index, event
from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry
from sqlmodel import (
    AutoString,
    Field,
    Session,
    SQLModel,
    Text,
    TypeDecorator,
    create_engine,
)

from clipforge import config
from clipforge.models import (
    BrandTemplate,
    CaptionStyle,
    Clip,
    ClipHook,
    ClipStatus,
    ClipTransitions,
    ClipVariant,
    CutRange,
    Framing,
    Job,
    JobKind,
    JobStatus,
    Layout,
    LogoPosition,
    ProcessingSettings,
    Project,
    SceneReframe,
    Scores,
    SourceRights,
    SourceSpan,
    Timeline,
    Word,
    ZoomKeyframe,
)

logger = logging.getLogger(__name__)

DB_FILENAME = "clipforge.db"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_MIGRATION_FILE = re.compile(r"^(\d{3})_(\w+)\.sql$")
_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
)
"""


class PydanticJSON(TypeDecorator[Any]):
    """A JSON text column whose values are validated by a Pydantic type.

    Writes accept a model or plain data, validate it, and store its JSON.
    Reads parse the JSON back into the Pydantic type (e.g. a Scores instance).
    In-place changes are not tracked: assign a new value to save a change.
    """

    impl = Text
    cache_ok = True

    def __init__(self, value_type: Any) -> None:
        super().__init__()
        self.value_type = value_type
        self._adapter: TypeAdapter[Any] = TypeAdapter(value_type)

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Validate a value and serialize it to JSON text."""
        if value is None:
            return None
        valid = self._adapter.validate_python(value)
        return self._adapter.dump_json(valid).decode()

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """Parse stored JSON text into the Pydantic type."""
        if value is None:
            return None
        return self._adapter.validate_json(value)


class ProjectRow(SQLModel, table=True):
    """A row of the project table; settings are stored as JSON."""

    __tablename__ = "project"

    id: int | None = Field(default=None, primary_key=True)
    source_url: str | None = None
    source_path: str
    title: str
    duration: float
    thumbnail_path: str
    settings: ProcessingSettings = Field(sa_type=PydanticJSON(ProcessingSettings))
    status: JobStatus = Field(default="queued", sa_type=AutoString)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_rights: SourceRights | None = Field(default=None, sa_type=AutoString)
    credit_line: str = ""
    campaign_id: int | None = None
    source_published_at: datetime | None = None
    result_set: int = 1
    overall_progress: float = 0.0
    eta_seconds: float | None = None
    opened_at: datetime | None = None
    archived_at: datetime | None = None

    def to_model(self) -> Project:
        """Return this row as a validated Project."""
        return Project.model_validate(self, from_attributes=True)


class ClipRow(SQLModel, table=True):
    """A row of the clip table; segments, tracks, lists and scores are stored
    as JSON."""

    __tablename__ = "clip"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", ondelete="CASCADE", index=True)
    segments: list[SourceSpan] = Field(sa_type=PydanticJSON(list[SourceSpan]))
    tracks: Timeline = Field(sa_type=PydanticJSON(Timeline))
    title: str
    hook_text: str
    description: str
    hashtags: list[str] = Field(sa_type=PydanticJSON(list[str]))
    emphasis_words: list[str] = Field(sa_type=PydanticJSON(list[str]))
    reason: str
    scores: Scores = Field(sa_type=PydanticJSON(Scores))
    layout: Layout = Field(sa_type=AutoString)
    caption_template: str
    caption_overrides: list[Word] = Field(
        default_factory=list, sa_type=PydanticJSON(list[Word])
    )
    cut_ranges: list[CutRange] = Field(
        default_factory=list, sa_type=PydanticJSON(list[CutRange])
    )
    status: ClipStatus = Field(default="candidate", sa_type=AutoString)
    output_path: str | None = None
    caption_style: CaptionStyle = Field(
        default_factory=CaptionStyle, sa_type=PydanticJSON(CaptionStyle)
    )
    crop_offset: float = 0.0
    framing: Framing = Field(default_factory=Framing, sa_type=PydanticJSON(Framing))
    auto_cut: bool = False
    auto_zoom: bool = False
    zoom_keyframes: list[ZoomKeyframe] = Field(
        default_factory=list, sa_type=PydanticJSON(list[ZoomKeyframe])
    )
    scene_reframes: list[SceneReframe] = Field(
        default_factory=list, sa_type=PydanticJSON(list[SceneReframe])
    )
    auto_color: bool = False
    show_captions: bool = True
    result_set: int = 1
    transitions: ClipTransitions = Field(
        default_factory=ClipTransitions, sa_type=PydanticJSON(ClipTransitions)
    )
    hook: ClipHook | None = Field(default=None, sa_type=PydanticJSON(ClipHook))
    enhance: float = 0.0
    parent_clip_id: int | None = Field(
        default=None, foreign_key="clip.id", ondelete="CASCADE", index=True
    )
    variant: ClipVariant = Field(default="original", sa_type=AutoString)

    def to_model(self) -> Clip:
        """Return this row as a validated Clip."""
        return Clip.model_validate(self, from_attributes=True)


class JobRow(SQLModel, table=True):
    """A row of the job table; clip_id is set for render jobs."""

    __tablename__ = "job"
    __table_args__ = (Index("ix_job_status_priority", "status", "priority"),)

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", ondelete="CASCADE", index=True)
    clip_id: int | None = Field(
        default=None, foreign_key="clip.id", ondelete="CASCADE", index=True
    )
    kind: JobKind = Field(sa_type=AutoString)
    step: str
    progress: float = 0.0
    status: JobStatus = Field(default="queued", sa_type=AutoString)
    error: str | None = None
    log_path: str
    priority: int = 0
    attempts: int = 0
    overall_progress: float = 0.0
    eta_seconds: float | None = None

    def to_model(self) -> Job:
        """Return this row as a validated Job."""
        return Job.model_validate(self, from_attributes=True)


class BrandTemplateRow(SQLModel, table=True):
    """A row of the brand_template table."""

    __tablename__ = "brand_template"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    logo_path: str
    logo_position: LogoPosition = Field(sa_type=AutoString)
    logo_opacity: float
    font: str
    primary_color: str
    intro_path: str | None = None
    outro_path: str | None = None

    def to_model(self) -> BrandTemplate:
        """Return this row as a validated BrandTemplate."""
        return BrandTemplate.model_validate(self, from_attributes=True)


def create_db_engine(data_dir: Path | None = None) -> Engine:
    """Return an engine for {data_dir}/clipforge.db, creating data_dir if needed.

    data_dir defaults to the configured settings.data_dir. Sessions record
    clip edits as versions from then on (clip_versions). SQLite enforces
    foreign keys (and so ON DELETE CASCADE) only on connections that enable
    them, so every new connection turns them on.
    """
    directory = config.settings.data_dir if data_dir is None else data_dir
    directory.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(directory / DB_FILENAME)))
    event.listen(engine, "connect", _enable_foreign_keys)
    from clipforge.clip_versions import install  # clip_versions imports db

    install()
    return engine


def init_db(data_dir: Path | None = None) -> Engine:
    """Return the engine for {data_dir}/clipforge.db with all migrations applied
    and the bundled fonts, music and sound effects in the asset library."""
    from clipforge.assets import (  # assets imports db
        register_bundled_fonts,
        register_bundled_music,
        register_bundled_sfx,
    )

    engine = create_db_engine(data_dir)
    migrate(engine)
    with Session(engine) as session:
        register_bundled_fonts(session)
        register_bundled_music(session)
        register_bundled_sfx(session)
    return engine


def _enable_foreign_keys(
    dbapi_connection: DBAPIConnection, connection_record: ConnectionPoolEntry
) -> None:
    """Turn on foreign key enforcement for a new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class MigrationError(RuntimeError):
    """A migration file is misnamed or would leave the database inconsistent."""


@dataclass(frozen=True)
class Migration:
    """A SQL migration file named NNN_name.sql."""

    version: int
    name: str
    path: Path


def migrate(engine: Engine, directory: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply pending migrations in version order and return their versions.

    Applied versions are recorded in schema_version, so a second run applies
    nothing. Each migration commits together with its schema_version row in
    one transaction; a failing migration leaves no partial changes and stops
    the run. Foreign keys are not enforced while migrating (SQLite ignores the
    pragma inside a transaction, and rebuilding a table would cascade deletes),
    so a migration that leaves a foreign key violation is rolled back.
    """
    migrations = _discover_migrations(directory)
    pooled = engine.raw_connection()
    try:
        conn = pooled.driver_connection
        if not isinstance(conn, sqlite3.Connection):
            raise MigrationError("migrations need a sqlite3 connection")
        conn.execute(_SCHEMA_VERSION_DDL)
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
        pending = [m for m in migrations if m.version not in applied]
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            for migration in pending:
                _apply(conn, migration)
        finally:
            conn.execute("PRAGMA foreign_keys=ON")
        return [m.version for m in pending]
    finally:
        pooled.close()


def _discover_migrations(directory: Path) -> list[Migration]:
    """Return the migrations in a directory, sorted by version.

    Every *.sql file must be named NNN_name.sql with a unique version, so a
    misnamed file fails loudly instead of being skipped.
    """
    if not directory.is_dir():
        raise MigrationError(f"migrations directory not found: {directory}")
    migrations = []
    for path in directory.glob("*.sql"):
        match = _MIGRATION_FILE.match(path.name)
        if match is None:
            raise MigrationError(f"{path.name} is not named NNN_name.sql")
        migrations.append(Migration(int(match[1]), match[2], path))
    migrations.sort(key=lambda m: m.version)
    for previous, current in pairwise(migrations):
        if previous.version == current.version:
            raise MigrationError(
                f"{previous.path.name} and {current.path.name} share a version"
            )
    return migrations


def _apply(conn: sqlite3.Connection, migration: Migration) -> None:
    """Run one migration and record it in schema_version in one transaction."""
    script = migration.path.read_text(encoding="utf-8")
    try:
        # executescript() commits any open transaction before it runs, so the
        # BEGIN must be part of the script; it stays open until commit().
        conn.executescript(f"BEGIN IMMEDIATE;\n{script}")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise MigrationError(
                f"{migration.path.name} leaves foreign key violations: {violations}"
            )
        conn.execute(
            "INSERT INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, datetime.now(UTC).isoformat()),
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    logger.info("Applied migration %s", migration.path.name)
