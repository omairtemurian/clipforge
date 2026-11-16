"""SQLModel rows of the collections (migration 030_v2_collections)."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from clipforge.watch.times import as_utc


class CollectionRow(SQLModel, table=True):
    """A row of the collection table."""

    __tablename__ = "collection"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def created(self) -> datetime:
        """Return when the collection was made, in UTC."""
        return as_utc(self.created_at)

    def updated(self) -> datetime:
        """Return when the collection last changed, in UTC."""
        return as_utc(self.updated_at)


class CollectionItemRow(SQLModel, table=True):
    """A row of the collection_item table: a clip in a collection."""

    __tablename__ = "collection_item"

    id: int | None = Field(default=None, primary_key=True)
    collection_id: int = Field(foreign_key="collection.id", ondelete="CASCADE")
    clip_id: int = Field(foreign_key="clip.id", ondelete="CASCADE", index=True)
    position: int
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
