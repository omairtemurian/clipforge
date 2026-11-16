"""The version history of a clip (SPEC-v2 3.5): undo/redo, autosave and
version restore.

Every edit of a clip stores a version: a session hook (install) sees each
flush that changes a ClipState field of a clip row, whichever code made
it, and adds the clip's new state as its current version. The first edit
first stores the clip as it was (its original version). Undo and redo move
the current version back and forward and give the clip that version's
state; an edit after an undo drops the versions after the current one.
Restore gives the clip an earlier version's state as a new version. A clip
keeps its latest config.settings.clip_versions_kept versions.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import instance_state
from sqlmodel import AutoString, Field, SQLModel

from clipforge import config
from clipforge.db import ClipRow, PydanticJSON
from clipforge.models import (
    ClipHistory,
    ClipState,
    ClipVersion,
    ClipVersionInfo,
    ClipVersionKind,
)
from clipforge.watch.times import as_utc

STATE_FIELDS = tuple(ClipState.model_fields)
# A session whose info has this key set does not record edits (history moves).
_PAUSED = "clip_versions_paused"


class ClipVersionRow(SQLModel, table=True):
    """A row of the clip_version table (migration 023_v2_clip_versions);
    fields and state are JSON."""

    __tablename__ = "clip_version"

    id: int | None = Field(default=None, primary_key=True)
    clip_id: int = Field(foreign_key="clip.id", ondelete="CASCADE")
    number: int
    kind: ClipVersionKind = Field(sa_type=AutoString)
    restored_from: int | None = None
    fields: list[str] = Field(default_factory=list, sa_type=PydanticJSON(list[str]))
    state: ClipState = Field(sa_type=PydanticJSON(ClipState))
    current: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def info(self) -> ClipVersionInfo:
        """Return this version without its state."""
        return ClipVersionInfo(
            number=self.number,
            kind=self.kind,
            created_at=as_utc(self.created_at),
            fields=self.fields,
            restored_from=self.restored_from,
        )

    def to_model(self) -> ClipVersion:
        """Return this version with its state."""
        return ClipVersion(**self.info().model_dump(), state=self.state)


class HistoryError(ValueError):
    """There is no version to undo or redo to; the message says why."""


def install() -> None:
    """Record clip edits in every session from now on (idempotent)."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)


def clip_state(row: ClipRow) -> ClipState:
    """Return the state of the clip row (its ClipState fields)."""
    return ClipState.model_validate(row, from_attributes=True)


def history(session: Session, clip_id: int) -> ClipHistory:
    """Return the history of clip clip_id (no versions before its first
    edit)."""
    versions = _versions(session, clip_id)
    current = _current(versions)
    number = current.number if current else 0
    return ClipHistory(
        current=number,
        can_undo=any(v.number < number for v in versions),
        can_redo=any(v.number > number for v in versions),
        versions=[v.info() for v in versions],
    )


def version(session: Session, clip_id: int, number: int) -> ClipVersion | None:
    """Return version number of clip clip_id, or None if it has none."""
    row = _version_row(session, clip_id, number)
    return row.to_model() if row else None


def undo(session: Session, row: ClipRow) -> None:
    """Give the clip row the state of the version before its current one,
    make that one current and commit. Raises HistoryError if there is
    none."""
    versions = _versions(session, _clip_id(row))
    current = _current(versions)
    earlier = [v for v in versions if current and v.number < current.number]
    if current is None or not earlier:
        raise HistoryError(f"clip {row.id} has nothing to undo")
    _move(session, row, current, earlier[-1])


def redo(session: Session, row: ClipRow) -> None:
    """Give the clip row the state of the version after its current one,
    make that one current and commit. Raises HistoryError if there is
    none."""
    versions = _versions(session, _clip_id(row))
    current = _current(versions)
    later = [v for v in versions if current and v.number > current.number]
    if current is None or not later:
        raise HistoryError(f"clip {row.id} has nothing to redo")
    _move(session, row, current, later[0])


def restore(session: Session, row: ClipRow, number: int) -> None:
    """Give the clip row the state of its version number, exactly, store it
    as a new restore version (unless the clip already has that state) and
    commit. Raises LookupError if the clip has no version number."""
    target = _version_row(session, _clip_id(row), number)
    if target is None:
        raise LookupError(f"clip {row.id} has no version {number}")
    _set_state(row, target.state)
    session.info[_PAUSED] = True
    try:
        _record(session, row, "restore", number)
        session.flush()
    finally:
        session.info.pop(_PAUSED, None)
    session.commit()
    session.refresh(row)


def _before_flush(session: Session, flush_context: Any, instances: Any) -> None:
    """Store a version of each clip whose state this flush changes."""
    if session.info.get(_PAUSED):
        return
    for obj in list(session.dirty):
        if isinstance(obj, ClipRow) and obj.id is not None and _state_changed(obj):
            _record(session, obj, "edit", None)


def _state_changed(row: ClipRow) -> bool:
    """Whether a ClipState field of row was set since it was loaded."""
    attrs = instance_state(row).attrs
    return any(attrs[name].history.has_changes() for name in STATE_FIELDS)


def _record(
    session: Session, row: ClipRow, kind: ClipVersionKind, restored_from: int | None
) -> None:
    """Add row's state as its current version (kind, restored_from) unless
    it is the current version's state. A clip without versions first gets
    its stored state as the original version. The versions after the
    current one are dropped, and the oldest beyond clip_versions_kept."""
    clip_id = _clip_id(row)
    new = clip_state(row)
    with session.no_autoflush:
        versions = _versions(session, clip_id)
        current = _current(versions)
        if current is None:
            stored = _stored_state(session, clip_id)
            if stored is None or stored == new:
                return
            current = ClipVersionRow(
                clip_id=clip_id, number=1, kind="original", state=stored
            )
            session.add(current)
            versions = [current]
        if current.state == new:
            return
        number = max(v.number for v in versions) + 1
        for later in [v for v in versions if v.number > current.number]:
            session.delete(later)
            versions.remove(later)
        current.current = False
        added = ClipVersionRow(
            clip_id=clip_id,
            number=number,
            kind=kind,
            restored_from=restored_from,
            fields=_changed_fields(current.state, new),
            state=new,
            current=True,
        )
        session.add(added)
        extra = len(versions) + 1 - config.settings.clip_versions_kept
        for old in versions[: max(extra, 0)]:
            session.delete(old)


def _move(
    session: Session, row: ClipRow, current: ClipVersionRow, target: ClipVersionRow
) -> None:
    """Make target the current version instead of current, give row its
    state and commit, without recording an edit."""
    current.current = False
    target.current = True
    _set_state(row, target.state)
    session.info[_PAUSED] = True
    try:
        session.flush()
    finally:
        session.info.pop(_PAUSED, None)
    session.commit()
    session.refresh(row)


def _set_state(row: ClipRow, state: ClipState) -> None:
    """Set row's ClipState fields to state's."""
    for name in STATE_FIELDS:
        setattr(row, name, getattr(state, name))


def _changed_fields(old: ClipState, new: ClipState) -> list[str]:
    """Return the names of the ClipState fields that differ in old and new."""
    return [name for name in STATE_FIELDS if getattr(old, name) != getattr(new, name)]


def _stored_state(session: Session, clip_id: int) -> ClipState | None:
    """Return the state of clip clip_id as the database has it now (before
    this flush), or None if it has no row yet."""
    table = SQLModel.metadata.tables[ClipRow.__tablename__]
    query = select(*(table.c[name] for name in STATE_FIELDS)).where(
        table.c.id == clip_id
    )
    stored = session.connection().execute(query).first()
    if stored is None:
        return None
    return ClipState.model_validate(stored._asdict())


def _versions(session: Session, clip_id: int) -> list[ClipVersionRow]:
    """Return the versions of clip clip_id, oldest first."""
    query = (
        select(ClipVersionRow)
        .where(ClipVersionRow.clip_id == clip_id)  # type: ignore[arg-type]
        .order_by(ClipVersionRow.number)  # type: ignore[arg-type]
    )
    return list(session.scalars(query))


def _version_row(session: Session, clip_id: int, number: int) -> ClipVersionRow | None:
    """Return version number of clip clip_id, or None."""
    return next((v for v in _versions(session, clip_id) if v.number == number), None)


def _current(versions: list[ClipVersionRow]) -> ClipVersionRow | None:
    """Return the current version of versions, or None if there are none."""
    return next((v for v in versions if v.current), versions[-1] if versions else None)


def _clip_id(row: ClipRow) -> int:
    """Return the id of a stored clip row."""
    if row.id is None:
        raise ValueError("the clip is not stored yet")
    return row.id
