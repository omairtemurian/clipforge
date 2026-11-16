"""SQLModel row of the search state (migration 031_v2_search)."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class SearchStateRow(SQLModel, table=True):
    """A row of the search_state table: the transcript file that a project's
    rows in the search index were made from."""

    __tablename__ = "search_state"

    project_id: int = Field(
        foreign_key="project.id", ondelete="CASCADE", primary_key=True
    )
    transcript_mtime_ns: int
    transcript_size: int
    segment_count: int
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
