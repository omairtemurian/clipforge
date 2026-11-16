"""Resumable chunked uploads of local videos (SPEC-v2 3.1), up to 30 GB.

An upload session is a directory {data_dir}/upload_sessions/<id>/ holding
meta.json (the file name and declared size) and data.part (the bytes
received so far). Its offset is the size of data.part, so a client that lost
its connection asks for the session and resends from that offset. Each chunk
carries its SHA-256 and is written only if it matches. When every byte is
in, finish() moves the file to {data_dir}/uploads/<random id>/<its name>,
where the projects of uploaded videos keep their source.
"""

import hashlib
import json
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from clipforge import config

UPLOADS_DIRNAME = "uploads"
SESSIONS_DIRNAME = "upload_sessions"
MAX_UPLOAD_BYTES = 30 * 1024**3
MAX_CHUNK_BYTES = 64 * 1024**2
# Free space kept beyond the upload itself (the database, job files).
DISK_MARGIN_BYTES = 512 * 1024**2
_META = "meta.json"
_DATA = "data.part"
_SESSION_ID = re.compile(r"[0-9a-f]{32}")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class UploadError(Exception):
    """A refused upload request; status and code are those of the API error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class UploadState:
    """An upload session: its id, file name, declared size and bytes received."""

    id: str
    filename: str
    size: int
    offset: int


def uploads_dir() -> Path:
    """Return the directory of the uploaded videos."""
    return config.settings.data_dir / UPLOADS_DIRNAME


def sessions_dir() -> Path:
    """Return the directory of the unfinished upload sessions."""
    return config.settings.data_dir / SESSIONS_DIRNAME


def free_bytes(path: Path) -> int:
    """Return the free bytes of the disk that holds path."""
    return shutil.disk_usage(path).free


def create(filename: str, size: int) -> UploadState:
    """Open a session for a file of size bytes.

    Only the last component of filename is kept. Raises UploadError 422 for an
    empty or over-30-GB size and 507 insufficient_storage if the disk lacks
    size plus DISK_MARGIN_BYTES of free space.
    """
    name = Path(filename.replace("\\", "/")).name or "upload"
    if size <= 0:
        raise UploadError(422, "validation_error", f"size: {name} is empty")
    if size > MAX_UPLOAD_BYTES:
        raise UploadError(
            422,
            "validation_error",
            f"size: {name} is larger than the 30 GB upload limit",
        )
    root = sessions_dir()
    root.mkdir(parents=True, exist_ok=True)
    free = free_bytes(root)
    if free < size + DISK_MARGIN_BYTES:
        raise UploadError(
            507,
            "insufficient_storage",
            f"Not enough free disk space for {name}: it needs "
            f"{_gb(size + DISK_MARGIN_BYTES)} and {_gb(free)} is free.",
        )
    session_id = uuid.uuid4().hex
    folder = root / session_id
    folder.mkdir()
    (folder / _META).write_text(json.dumps({"filename": name, "size": size}))
    (folder / _DATA).touch()
    return UploadState(session_id, name, size, 0)


def status(session_id: str) -> UploadState:
    """Return the session; UploadError 404 if there is none with that id."""
    folder = _folder(session_id)
    meta = json.loads((folder / _META).read_text())
    return UploadState(
        session_id,
        str(meta["filename"]),
        int(meta["size"]),
        (folder / _DATA).stat().st_size,
    )


def append(session_id: str, offset: int, chunk: bytes, sha256: str) -> UploadState:
    """Write chunk at offset and return the session.

    UploadError 409 offset_mismatch unless offset is the bytes received so far
    (the client then resumes from the session's offset), 422
    checksum_mismatch if chunk's SHA-256 is not sha256 (hex), 422
    validation_error for an empty chunk or one that passes the declared size.
    """
    with _lock(session_id):
        state = status(session_id)
        if offset != state.offset:
            raise UploadError(
                409,
                "offset_mismatch",
                f"offset {offset} does not match the {state.offset} bytes received",
            )
        if not chunk:
            raise UploadError(422, "validation_error", "the chunk is empty")
        if offset + len(chunk) > state.size:
            raise UploadError(
                422,
                "validation_error",
                f"the chunk passes the declared size of {state.size} bytes",
            )
        if hashlib.sha256(chunk).hexdigest() != sha256.strip().lower():
            raise UploadError(
                422, "checksum_mismatch", "the chunk's SHA-256 does not match"
            )
        with (_folder(session_id) / _DATA).open("ab") as out:
            out.write(chunk)
        return UploadState(state.id, state.filename, state.size, offset + len(chunk))


def finish(session_id: str) -> Path:
    """Move the complete file to its uploads directory, drop the session and
    return the file's path; UploadError 409 upload_incomplete if bytes are
    missing."""
    with _lock(session_id):
        state = status(session_id)
        if state.offset != state.size:
            raise UploadError(
                409,
                "upload_incomplete",
                f"{state.offset} of {state.size} bytes received; send the rest first",
            )
        folder = _folder(session_id)
        target = uploads_dir() / uuid.uuid4().hex / state.filename
        target.parent.mkdir(parents=True)
        (folder / _DATA).rename(target)
        shutil.rmtree(folder)
    _forget_lock(session_id)
    return target


def cancel(session_id: str) -> None:
    """Delete the session and its bytes; UploadError 404 if there is none."""
    with _lock(session_id):
        shutil.rmtree(_folder(session_id))
    _forget_lock(session_id)


def _folder(session_id: str) -> Path:
    """Return the directory of an existing session (404 UploadError if none)."""
    folder = sessions_dir() / session_id
    if not _SESSION_ID.fullmatch(session_id) or not (folder / _META).is_file():
        raise UploadError(404, "not_found", f"upload {session_id} not found")
    return folder


def _lock(session_id: str) -> threading.Lock:
    """Return the lock that serializes the writes of one session."""
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


def _forget_lock(session_id: str) -> None:
    with _locks_guard:
        _locks.pop(session_id, None)


def _gb(size: int) -> str:
    return f"{size / 1024**3:.1f} GB"
