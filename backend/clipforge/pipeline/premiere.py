"""Premiere export (SPEC 6.12): a project's clips as Final Cut Pro 7 XML.

Premiere Pro imports Final Cut Pro 7 XML (xmeml); build_xmeml writes its
version 4, the one that Premiere writes. The document's project, named after
the source video, holds a sequence for each clip, in order (best first), at
the source's frame size and rate. A sequence plays its clip's [start, end]
seconds of the source once: its video track and its audio tracks each hold
one clipitem that plays source frames in = round(start * fps) to
out = round(end * fps) (out not included) from the sequence's first frame,
and the clipitems are linked. The audio tracks are the one channel of a mono
source, or else a stereo pair of its first two channels, as Premiere lays out
stereo. An editor gets each clip's in and out points on the source; cuts
(filler removal), layouts and captions are not part of the XML.

fps is the rate that the XML states (xml_rate): a whole timebase, flagged
ntsc for the NTSC rate timebase * 1000/1001 (29.97 is timebase 30 with ntsc),
which is the source's own rate if that is a standard one. The clipitems play
the job's source.mp4, which the first <file> describes in full, naming it by
a file://localhost URL (path_url); the others refer to it by its id.
"""

import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.ffmpeg import probe_media
from clipforge.models import Clip, SourceMeta
from clipforge.pipeline.step import (
    SOURCE,
    StepError,
    load_meta,
    missing_input,
    write_text,
)

XMEML_VERSION = "4"
PROLOGUE = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
FILE_ID = "file-1"
# The audio sample depth that the XML states; AAC has none of its own.
AUDIO_DEPTH = 16
# A stereo pair: the most audio tracks that a sequence plays.
MAX_AUDIO_TRACKS = 2
# Characters that XML 1.0 does not allow, which a title might hold.
NOT_XML = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


@dataclass(frozen=True)
class Rate:
    """A frame rate as xmeml states it: timebase frames a second, or
    timebase * 1000/1001 if ntsc."""

    timebase: int
    ntsc: bool

    @property
    def fps(self) -> float:
        """Return the frames a second of this rate."""
        return self.timebase * 1000 / 1001 if self.ntsc else float(self.timebase)

    def frame(self, seconds: float) -> int:
        """Return the number of the frame at seconds: round(seconds * fps)."""
        return round(seconds * self.fps)


@dataclass(frozen=True)
class Source:
    """The source video that the clips play: its path, what ingest found out
    about it (meta.json) and the sample rate and channel count of its audio."""

    path: Path
    meta: SourceMeta
    sample_rate: int
    channels: int

    @property
    def rate(self) -> Rate:
        """Return the rate that the XML states for the video (xml_rate)."""
        return xml_rate(self.meta.fps)

    @property
    def audio_tracks(self) -> int:
        """Return the number of audio tracks that a sequence plays: 1 for a
        mono source, 2 (a stereo pair) for any other."""
        return min(self.channels, MAX_AUDIO_TRACKS)


def xml_rate(fps: float) -> Rate:
    """Return the Rate that states fps frames a second: the nearest whole
    timebase (at least 1), with ntsc if fps is nearer to
    timebase * 1000/1001 than to timebase (29.97 -> 30 with ntsc)."""
    timebase = max(1, round(fps))
    ntsc = abs(fps - timebase * 1000 / 1001) < abs(fps - timebase)
    return Rate(timebase, ntsc)


def path_url(path: Path) -> str:
    """Return the file://localhost URL of path, made absolute, with each
    character but letters, digits, "_.-~" and "/" percent-encoded (UTF-8)."""
    return "file://localhost" + urllib.parse.quote(str(path.absolute()), safe="/")


def read_source(work: Path) -> Source:
    """Return the Source of the job work directory work: its source.mp4,
    which meta.json describes and whose audio ffprobe reads.

    Raises StepError if meta.json or source.mp4 is missing, meta.json is not
    valid or source.mp4 has no audio, and FFmpegError if ffprobe cannot read
    source.mp4.
    """
    meta = load_meta(work)
    path = work / SOURCE
    if not path.is_file():
        raise missing_input(path, "ingest")
    info = probe_media(path)
    if info.sample_rate is None or info.channels is None:
        raise StepError(f"{path} has no audio stream")
    return Source(path, meta, info.sample_rate, info.channels)


def build_xmeml(clips: Sequence[Clip], source: Source) -> str:
    """Return the xmeml document of clips, in order, on source (see the
    module docstring).

    Sequence n is named by n, zero-padded to two digits or more, and its
    clip's title. Its clipitems, numbered on through the document, are its
    video one and then its audio ones.
    """
    root = ET.Element("xmeml", version=XMEML_VERSION)
    project = _add(root, "project")
    _add(project, "name", source.meta.title)
    children = _add(project, "children")
    items = 1 + source.audio_tracks
    digits = max(2, len(str(len(clips))))
    for index, clip in enumerate(clips):
        ids = [f"clipitem-{index * items + item}" for item in range(1, items + 1)]
        sequence = _add(children, "sequence", id=f"sequence-{index + 1}")
        _add(sequence, "name", " ".join(f"{index + 1:0{digits}d} {clip.title}".split()))
        _add_tracks(sequence, clip, ids, source, describe_file=index == 0)
    ET.indent(root, space="\t")
    return PROLOGUE + ET.tostring(root, encoding="unicode") + "\n"


def write_premiere_xml(path: Path, clips: Sequence[Clip], work: Path) -> Path:
    """Write the xmeml document (build_xmeml) of clips on the source video of
    the job work directory work (read_source) to path and return path.

    Raises what read_source raises; then nothing is written.
    """
    text = build_xmeml(clips, read_source(work))
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, text)
    return path


def _add_tracks(
    sequence: ET.Element,
    clip: Clip,
    ids: Sequence[str],
    source: Source,
    *,
    describe_file: bool,
) -> None:
    """Add to sequence its length, rate and the tracks that play clip on
    source: a video track, then the audio tracks, with one clipitem each,
    whose ids are ids. The first clipitem describes the source file in full
    if describe_file, else it only refers to it."""
    rate, meta = source.rate, source.meta
    first, last = rate.frame(clip.start), rate.frame(clip.end)
    _add(sequence, "duration", last - first)
    _add_rate(sequence, rate)
    _add_timecode(sequence, rate)
    media = _add(sequence, "media")
    video = _add(media, "video")
    _add_video_characteristics(_add(video, "format"), source)
    audio = _add(media, "audio")
    _add_audio_characteristics(_add(audio, "format"), source)
    for index, item_id in enumerate(ids):
        track = _add(audio if index else video, "track")
        item = _add(track, "clipitem", id=item_id)
        _add(item, "name", meta.title)
        _add(item, "enabled", "TRUE")
        _add(item, "duration", rate.frame(meta.duration))
        _add_rate(item, rate)
        _add(item, "start", 0)
        _add(item, "end", last - first)
        _add(item, "in", first)
        _add(item, "out", last)
        _add_file(item, source, describe=describe_file and not index)
        if index:
            sourcetrack = _add(item, "sourcetrack")
            _add(sourcetrack, "mediatype", "audio")
            _add(sourcetrack, "trackindex", index)
        _add_links(item, ids)
        _add(track, "enabled", "TRUE")
        _add(track, "locked", "FALSE")
        if index and source.audio_tracks > 1:
            _add(track, "outputchannelindex", index)


def _add_file(item: ET.Element, source: Source, *, describe: bool) -> None:
    """Add the <file> of source to the clipitem item: in full if describe,
    else only its id."""
    file = _add(item, "file", id=FILE_ID)
    if not describe:
        return
    rate = source.rate
    _add(file, "name", source.meta.title)
    _add(file, "pathurl", path_url(source.path))
    _add_rate(file, rate)
    _add(file, "duration", rate.frame(source.meta.duration))
    _add_timecode(file, rate)
    media = _add(file, "media")
    _add_video_characteristics(_add(media, "video"), source)
    audio = _add(media, "audio")
    _add_audio_characteristics(audio, source)
    _add(audio, "channelcount", source.channels)


def _add_links(item: ET.Element, ids: Sequence[str]) -> None:
    """Add to the clipitem item the links of a sequence's clipitems ids,
    which move together: the video one on video track 1, then the audio ones
    on audio tracks 1, 2, ..., in one group (a stereo pair if two)."""
    for index, item_id in enumerate(ids):
        link = _add(item, "link")
        _add(link, "linkclipref", item_id)
        _add(link, "mediatype", "audio" if index else "video")
        _add(link, "trackindex", index or 1)
        _add(link, "clipindex", 1)
        if index:
            _add(link, "groupindex", 1)


def _add_rate(parent: ET.Element, rate: Rate) -> None:
    """Add the <rate> element of rate to parent."""
    element = _add(parent, "rate")
    _add(element, "timebase", rate.timebase)
    _add(element, "ntsc", "TRUE" if rate.ntsc else "FALSE")


def _add_timecode(parent: ET.Element, rate: Rate) -> None:
    """Add to parent a timecode at rate that starts at 00:00:00:00."""
    timecode = _add(parent, "timecode")
    _add_rate(timecode, rate)
    _add(timecode, "string", "00:00:00:00")
    _add(timecode, "frame", 0)
    _add(timecode, "displayformat", "NDF")


def _add_video_characteristics(parent: ET.Element, source: Source) -> None:
    """Add to parent the frame rate and size of source's video, in square
    pixels and not interlaced."""
    characteristics = _add(parent, "samplecharacteristics")
    _add_rate(characteristics, source.rate)
    _add(characteristics, "width", source.meta.width)
    _add(characteristics, "height", source.meta.height)
    _add(characteristics, "anamorphic", "FALSE")
    _add(characteristics, "pixelaspectratio", "square")
    _add(characteristics, "fielddominance", "none")


def _add_audio_characteristics(parent: ET.Element, source: Source) -> None:
    """Add to parent the sample depth and rate of source's audio."""
    characteristics = _add(parent, "samplecharacteristics")
    _add(characteristics, "depth", AUDIO_DEPTH)
    _add(characteristics, "samplerate", source.sample_rate)


def _add(
    parent: ET.Element, tag: str, text: str | int | None = None, **attrib: str
) -> ET.Element:
    """Add the element tag, with attrib and text if any, to parent and return
    it; characters that XML does not allow are left out of text."""
    element = ET.SubElement(parent, tag, attrib)
    if text is not None:
        element.text = NOT_XML.sub("", str(text))
    return element
