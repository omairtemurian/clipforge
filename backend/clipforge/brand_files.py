"""Files of a brand template: its logo, intro and outro, in
{data_dir}/brand/<template id>/ (SPEC 7).

The logo is checked by its first bytes and stored as logo.png, logo.jpg or
logo.webp; the name the client gave is never used as a path. Intro and
outro are videos, stored as intro<ext> and outro<ext> after ffprobe has
read them. An upload is first staged in a temporary directory, so that a
request with a bad file changes no file; publish then moves the staged
files into the template's directory, replacing the older ones.
"""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import UploadFile

from clipforge import config
from clipforge.api.errors import ApiError
from clipforge.ffmpeg import FFmpegError, probe_media

BRAND_DIRNAME = "brand"
MAX_LOGO_BYTES = 5 * 1024 * 1024
VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def brand_dir(template_id: int) -> Path:
    """Return the directory of a template's files."""
    return config.settings.data_dir / BRAND_DIRNAME / str(template_id)


def image_suffix(head: bytes) -> str | None:
    """Return .png, .jpg or .webp for the first bytes of such an image, else None."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


@contextmanager
def staging_dir() -> Iterator[Path]:
    """Yield a new empty directory for staged uploads; it is deleted after."""
    root = config.settings.data_dir / BRAND_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=root) as path:
        yield Path(path)


def stage_logo(staging: Path, file: UploadFile) -> Path:
    """Save an uploaded logo in staging as logo.<ext> and return its path.

    Raises the 422 ApiError if it is empty, over MAX_LOGO_BYTES or not a
    PNG, JPEG or WebP image.
    """
    data = file.file.read(MAX_LOGO_BYTES + 1)
    if not data:
        raise ApiError(422, "validation_error", "logo: the file is empty")
    if len(data) > MAX_LOGO_BYTES:
        raise ApiError(422, "validation_error", "logo: the file is over 5 MB")
    suffix = image_suffix(data[:12])
    if suffix is None:
        raise ApiError(422, "validation_error", "logo: must be a PNG, JPEG or WebP")
    target = staging / f"logo{suffix}"
    target.write_bytes(data)
    return target


def stage_video(staging: Path, file: UploadFile, kind: str) -> Path:
    """Save an uploaded intro or outro (kind) in staging as <kind><ext> and
    return its path.

    Raises the 422 ApiError if its name has no video suffix or ffprobe
    cannot read a video (with a duration) in it.
    """
    suffix = Path((file.filename or "").replace("\\", "/")).suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        known = ", ".join(VIDEO_SUFFIXES)
        raise ApiError(422, "validation_error", f"{kind}: name must end in {known}")
    target = staging / f"{kind}{suffix}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        probe_media(target)
    except (FFmpegError, KeyError, ValueError) as exc:
        raise ApiError(422, "validation_error", f"{kind}: not a video file") from exc
    return target


def final_path(template_id: int, staged: Path) -> Path:
    """Return where publish puts the staged file of template template_id."""
    return brand_dir(template_id) / staged.name


def publish(template_id: int, staged: list[Path]) -> None:
    """Move the staged files into the directory of template template_id; of
    each kind (logo, intro, outro) the older file is deleted."""
    directory = brand_dir(template_id)
    directory.mkdir(parents=True, exist_ok=True)
    for path in staged:
        for old in directory.glob(f"{path.stem}.*"):
            old.unlink()
        shutil.move(path, directory / path.name)


def remove_video(template_id: int, kind: str) -> None:
    """Delete the intro or outro (kind) of template template_id, if it has one."""
    for old in brand_dir(template_id).glob(f"{kind}.*"):
        old.unlink()


def remove_files(template_id: int) -> None:
    """Delete all files of template template_id."""
    shutil.rmtree(brand_dir(template_id), ignore_errors=True)
