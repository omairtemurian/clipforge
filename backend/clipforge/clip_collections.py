"""Collections of clips (SPEC-v2 3.11): create, rename and delete a
collection, add clips to it from anywhere (the gallery, a project's results,
a search) and remove them. The zip of a collection is clips collection_export.

Items keep the order they were added in (CollectionItemRow.position, from 0
and without gaps); a clip is in a collection once.
"""

from datetime import UTC, datetime

from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from clipforge.collection_rows import CollectionItemRow, CollectionRow
from clipforge.db import ClipRow
from clipforge.models import (
    Clip,
    Collection,
    CollectionClip,
    CollectionCreate,
    CollectionDetail,
    CollectionItem,
    CollectionUpdate,
)
from clipforge.watch.times import as_utc


class CollectionNotFound(LookupError):
    """There is no such collection."""


class ClipsNotFound(LookupError):
    """Some clips do not exist; ids lists them."""

    def __init__(self, ids: list[int]) -> None:
        super().__init__(f"clips not found: {', '.join(map(str, ids))}")
        self.ids = ids


class ItemNotFound(LookupError):
    """The clip is not in the collection."""


def _row(session: Session, collection_id: int) -> CollectionRow:
    row = session.get(CollectionRow, collection_id)
    if row is None:
        raise CollectionNotFound(f"collection {collection_id} does not exist")
    return row


def _model(row: CollectionRow, clip_count: int) -> Collection:
    return Collection(
        id=row.id or 0,
        name=row.name,
        description=row.description,
        created_at=row.created(),
        updated_at=row.updated(),
        clip_count=clip_count,
    )


def _count(session: Session, collection_id: int) -> int:
    return session.exec(
        select(func.count())
        .select_from(CollectionItemRow)
        .where(CollectionItemRow.collection_id == collection_id)
    ).one()


def create_collection(engine: Engine, body: CollectionCreate) -> CollectionDetail:
    """Make an empty collection and return it."""
    with Session(engine) as session:
        row = CollectionRow(name=body.name, description=body.description)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _detail(session, row)


def list_collections(engine: Engine) -> list[Collection]:
    """Return every collection, newest first (by id), with its clip count."""
    with Session(engine) as session:
        counts = dict(
            session.exec(
                select(CollectionItemRow.collection_id, func.count()).group_by(
                    col(CollectionItemRow.collection_id)
                )
            ).all()
        )
        rows = session.exec(
            select(CollectionRow).order_by(col(CollectionRow.id).desc())
        )
        return [_model(row, counts.get(row.id or 0, 0)) for row in rows]


def get_collection(engine: Engine, collection_id: int) -> CollectionDetail:
    """Return collection collection_id with its items in order;
    CollectionNotFound if there is none."""
    with Session(engine) as session:
        return _detail(session, _row(session, collection_id))


def update_collection(
    engine: Engine, collection_id: int, body: CollectionUpdate
) -> CollectionDetail:
    """Change the name and/or description of a collection (the fields that
    are set); CollectionNotFound if there is none."""
    with Session(engine) as session:
        row = _row(session, collection_id)
        changes = body.model_dump(exclude_none=True)
        for field, value in changes.items():
            setattr(row, field, value)
        if changes:
            row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _detail(session, row)


def delete_collection(engine: Engine, collection_id: int) -> None:
    """Delete a collection and its items (not the clips); CollectionNotFound
    if there is none."""
    with Session(engine) as session:
        session.delete(_row(session, collection_id))
        session.commit()


def add_clips(
    engine: Engine, collection_id: int, clip_ids: list[int]
) -> CollectionDetail:
    """Add clip_ids to the end of the collection, in order; clips that are
    in it already (or repeated in clip_ids) stay where they are.

    Raises CollectionNotFound if there is no such collection and ClipsNotFound
    (nothing is added) if some clips do not exist.
    """
    with Session(engine) as session:
        row = _row(session, collection_id)
        existing = set(
            session.exec(select(ClipRow.id).where(col(ClipRow.id).in_(clip_ids)))
        )
        missing = [
            clip_id for clip_id in dict.fromkeys(clip_ids) if clip_id not in existing
        ]
        if missing:
            raise ClipsNotFound(missing)
        present = set(
            session.exec(
                select(CollectionItemRow.clip_id).where(
                    CollectionItemRow.collection_id == collection_id
                )
            )
        )
        position = _count(session, collection_id)
        for clip_id in dict.fromkeys(clip_ids):
            if clip_id in present:
                continue
            session.add(
                CollectionItemRow(
                    collection_id=collection_id, clip_id=clip_id, position=position
                )
            )
            position += 1
        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _detail(session, row)


def remove_clip(engine: Engine, collection_id: int, clip_id: int) -> CollectionDetail:
    """Take a clip out of a collection (the rest keep their order) and
    return the collection.

    Raises CollectionNotFound if there is no such collection and ItemNotFound
    if the clip is not in it.
    """
    with Session(engine) as session:
        row = _row(session, collection_id)
        item = session.exec(
            select(CollectionItemRow).where(
                CollectionItemRow.collection_id == collection_id,
                CollectionItemRow.clip_id == clip_id,
            )
        ).first()
        if item is None:
            raise ItemNotFound(f"clip {clip_id} is not in collection {collection_id}")
        session.delete(item)
        session.flush()
        for position, rest in enumerate(_items(session, collection_id)):
            rest.position = position
            session.add(rest)
        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _detail(session, row)


def clip_of(engine: Engine, clip_id: int) -> Clip:
    """Return clip clip_id (a clip of a collection always exists)."""
    with Session(engine) as session:
        return session.get_one(ClipRow, clip_id).to_model()


def _items(session: Session, collection_id: int) -> list[CollectionItemRow]:
    return list(
        session.exec(
            select(CollectionItemRow)
            .where(CollectionItemRow.collection_id == collection_id)
            .order_by(col(CollectionItemRow.position), col(CollectionItemRow.id))
        )
    )


def _detail(session: Session, row: CollectionRow) -> CollectionDetail:
    collection_id = row.id or 0
    items: list[CollectionItem] = []
    for item in _items(session, collection_id):
        clip = session.get_one(ClipRow, item.clip_id).to_model()
        items.append(
            CollectionItem(
                id=item.id or 0,
                collection_id=collection_id,
                clip_id=item.clip_id,
                position=item.position,
                added_at=as_utc(item.added_at),
                clip=CollectionClip(
                    id=clip.id,
                    project_id=clip.project_id,
                    title=clip.title,
                    status=clip.status,
                    overall=clip.scores.overall,
                    start=clip.start,
                    end=clip.end,
                ),
            )
        )
    return CollectionDetail(**_model(row, len(items)).model_dump(), items=items)
