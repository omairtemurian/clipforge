"""API keys of the public REST API /api/v1 (SPEC-v2 2.5, 3.14, 4).

A key is "cfk_" plus 43 URL-safe characters (32 random bytes from
`secrets`). It is returned once, by create_key, and never stored: the
api_key table (migration 020_v2_api_keys) keeps its SHA-256 hex digest and
its first PREFIX_LENGTH characters. A key carries 256 random bits, so a
plain SHA-256 cannot be reversed or guessed; a slow password hash (argon2)
would only slow down every API request (docs/decisions.md, TASK-164).
authenticate finds a key's row by its digest and records when it was used;
deleting the row revokes the key.
"""

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, col, select

from clipforge.models import ApiKey, ApiKeyCreated
from clipforge.watch.times import as_utc

KEY_PREFIX = "cfk_"
KEY_BYTES = 32
PREFIX_LENGTH = 10


class ApiKeyNotFound(LookupError):
    """There is no such API key."""


class ApiKeyRow(SQLModel, table=True):
    """A row of the api_key table: a key's name, prefix and digest."""

    __tablename__ = "api_key"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    prefix: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    key_hash: str = Field(unique=True)

    def to_model(self) -> ApiKey:
        """Return this row as an ApiKey (without its digest), times in UTC."""
        return ApiKey(
            id=self.id or 0,
            name=self.name,
            prefix=self.prefix,
            created_at=as_utc(self.created_at),
            last_used_at=None
            if self.last_used_at is None
            else as_utc(self.last_used_at),
        )


def hash_key(key: str) -> str:
    """Return the SHA-256 hex digest of key, as stored in api_key.key_hash."""
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    """Return a new random API key."""
    return KEY_PREFIX + secrets.token_urlsafe(KEY_BYTES)


def create_key(engine: Engine, name: str) -> ApiKeyCreated:
    """Make and store a new key named name; the result holds the key itself,
    which cannot be read back later."""
    key = new_key()
    row = ApiKeyRow(name=name, prefix=key[:PREFIX_LENGTH], key_hash=hash_key(key))
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return ApiKeyCreated(**row.to_model().model_dump(), key=key)


def list_keys(engine: Engine) -> list[ApiKey]:
    """Return every key (without the key itself), oldest first."""
    with Session(engine) as session:
        rows = session.exec(select(ApiKeyRow).order_by(col(ApiKeyRow.id)))
        return [row.to_model() for row in rows]


def delete_key(engine: Engine, key_id: int) -> None:
    """Revoke key key_id; ApiKeyNotFound if there is none."""
    with Session(engine) as session:
        row = session.get(ApiKeyRow, key_id)
        if row is None:
            raise ApiKeyNotFound(f"API key {key_id} does not exist")
        session.delete(row)
        session.commit()


def authenticate(
    engine: Engine, key: str, now: datetime | None = None
) -> ApiKey | None:
    """Return the stored key that key is (its last_used_at set to now), or
    None if key is not one of them."""
    with Session(engine) as session:
        row = session.exec(
            select(ApiKeyRow).where(col(ApiKeyRow.key_hash) == hash_key(key))
        ).first()
        if row is None:
            return None
        row.last_used_at = now or datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()
