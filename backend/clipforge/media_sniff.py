"""What an uploaded media file is, from its first bytes (never from the name
or the Content-Type the client gave): a PNG, JPEG, WebP or GIF image, or a
video or audio container. ffprobe then decides if a container holds video or
only audio (media_library)."""

from dataclasses import dataclass

# The bytes that sniff reads.
HEAD_BYTES = 4096
EBML_MAGIC = b"\x1a\x45\xdf\xa3"
# The MIME subtype of each file suffix; its type is image, video or audio.
SUBTYPES = {
    ".png": "png",
    ".jpg": "jpeg",
    ".webp": "webp",
    ".gif": "gif",
    ".mp4": "mp4",
    ".m4a": "mp4",
    ".mov": "quicktime",
    ".mkv": "x-matroska",
    ".webm": "webm",
    ".avi": "x-msvideo",
    ".mp3": "mpeg",
    ".wav": "wav",
    ".ogg": "ogg",
    ".flac": "flac",
    ".aac": "aac",
}


@dataclass(frozen=True)
class Sniffed:
    """The suffix a file is stored with and whether it is an image."""

    suffix: str
    image: bool


def sniff(head: bytes) -> Sniffed | None:
    """Return what the first bytes of a file say it is, or None if they match
    no image, video or audio format that the library takes."""
    suffix = _image_suffix(head)
    if suffix is not None:
        return Sniffed(suffix, True)
    suffix = _container_suffix(head)
    return None if suffix is None else Sniffed(suffix, False)


def mime_type(suffix: str, kind: str) -> str:
    """Return the MIME type of a file with suffix whose asset kind is kind."""
    family = "image" if kind in ("image", "logo") else kind
    return f"{family}/{SUBTYPES[suffix]}"


def _image_suffix(head: bytes) -> str | None:
    """Return the suffix of the image format that head starts, if any."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


def _container_suffix(head: bytes) -> str | None:
    """Return the suffix of the video or audio format that head starts."""
    if head[4:8] == b"ftyp":
        return {b"qt  ": ".mov", b"M4A ": ".m4a"}.get(head[8:12], ".mp4")
    if head.startswith(EBML_MAGIC):
        return ".webm" if b"webm" in head[:64] else ".mkv"
    if head[:4] == b"RIFF":
        return {b"AVI ": ".avi", b"WAVE": ".wav"}.get(head[8:12])
    if head.startswith(b"OggS"):
        return ".ogg"
    if head.startswith(b"fLaC"):
        return ".flac"
    if head.startswith(b"ID3"):
        return ".mp3"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0:
        # MPEG audio frames; layer bits 00 mean AAC in an ADTS stream.
        return ".aac" if head[1] & 0x06 == 0 else ".mp3"
    return None
