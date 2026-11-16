"""Export (SPEC 6.12): a rendered clip's subtitles and metadata, and zips.

Next to a rendered clip's video, {data_dir}/output/{project_id}/{clip_id}.mp4
(render.clip_output), export writes:

- {clip_id}.srt (write_srt): SubRip subtitles of the captions that the
  render burns in. The words are the clip's caption words after its cuts
  (polish.rendered_words), in the lines of its caption template
  (caption_lines.group_lines with max_words_per_line), and a cue shows a
  line from its first word's start until its last word stops being active
  (caption_lines.active_end), as the burnt-in line does. Cue text keeps the
  transcript's case, without the template's uppercase, emoji or the hook.
  Cues are numbered from 1, each "index", "start --> end" (HH:MM:SS,mmm) and
  its text on one line, then a blank line, as ffmpeg's SRT muxer writes
  them; UTF-8 with LF line ends.
- {clip_id}.json (write_metadata): the clip's title, description, hashtags
  (as stored, without "#") and credit line (credit_line): credit_template
  filled with the channel, channel_url and title (of the source video) in
  meta.json, or null if one that it uses is unknown, as the channel of a
  local file is.

write_zip packs files into a zip archive, such as a project's rendered
clips with their exports (clipforge.clips.export_project). The Premiere XML
of a project's clips is written by pipeline/premiere.

export_output names the MP4 that clipforge.clip_export renders at a chosen
resolution or for a platform preset (clipforge.export_presets), next to the
clip's own render but in the project's exports directory.
"""

import json
import logging
import os
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

from clipforge.captions_templates import get_template
from clipforge.config import credit_fields
from clipforge.models import Clip, SourceMeta, Transcript
from clipforge.pipeline.caption_lines import CaptionWord, active_end, group_lines
from clipforge.pipeline.polish import rendered_words
from clipforge.pipeline.render import project_output
from clipforge.pipeline.step import TRANSCRIPT, load_json, load_meta, write_text

logger = logging.getLogger(__name__)


class Cue(NamedTuple):
    """A subtitle cue: its start and end in milliseconds and its one-line
    text."""

    start: int
    end: int
    text: str


# The directory of a project's exports, in its output directory.
EXPORTS_DIRNAME = "exports"
# Files that a zip stores as they are: their data is compressed already.
STORED_SUFFIXES = frozenset({".mp4"})


def srt_time(time: int) -> str:
    """Return time, in milliseconds, as an SRT timestamp: 61415 ->
    00:01:01,415."""
    seconds, millis = divmod(time, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def caption_cues(words: Sequence[CaptionWord], max_words: int) -> list[Cue]:
    """Return the subtitle cues of words, in milliseconds from a clip's start,
    with a cue for each caption line of at most max_words words.

    A line shows from its first word's start until its last word stops being
    active; a line that would show for no time gets no cue. A cue's text is
    the line's words on one line.
    """
    lines = group_lines(words, max_words)
    cues: list[Cue] = []
    for position, line in enumerate(lines):
        following = lines[position + 1][0] if position + 1 < len(lines) else None
        start, end = line[0].start, active_end(line[-1], following)
        if end <= start:
            continue
        text = " ".join(" ".join(word.text for word in line).split())
        cues.append(Cue(start, end, text))
    return cues


def build_srt(words: Sequence[CaptionWord], max_words: int) -> str:
    """Return the SRT subtitles of words (caption_cues): each cue as "index",
    "start --> end" and its text, then a blank line."""
    cues = caption_cues(words, max_words)
    return "".join(
        f"{number}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{cue.text}\n\n"
        for number, cue in enumerate(cues, 1)
    )


def credit_line(template: str, meta: SourceMeta) -> str | None:
    """Return template, a credit_template, filled with the channel,
    channel_url and title of meta, or None if a field that it uses is
    unknown (None) or the line is blank.

    Raises ValueError if template uses anything but those fields
    (config.credit_fields).
    """
    values: dict[str, str | None] = {
        "channel": meta.channel,
        "channel_url": meta.channel_url,
        "title": meta.title,
    }
    if any(values[field] is None for field in credit_fields(template)):
        return None
    line = template.format_map(values).strip()
    return line or None


def clip_metadata(clip: Clip, credit: str | None) -> dict[str, object]:
    """Return the metadata of clip with its credit line, as its JSON holds."""
    return {
        "title": clip.title,
        "description": clip.description,
        "hashtags": list(clip.hashtags),
        "credit": credit,
    }


def rendered_video(clip: Clip) -> Path:
    """Return the path of clip's rendered video; raises ValueError if it has
    none."""
    if clip.output_path is None:
        raise ValueError(f"clip {clip.id} has no rendered video")
    return Path(clip.output_path)


def export_output(project_id: int, clip_id: int, tag: str) -> Path:
    """Return the path of clip clip_id's export tagged tag (a preset id or a
    resolution): {project output}/exports/{clip_id}-{tag}.mp4."""
    return project_output(project_id) / EXPORTS_DIRNAME / f"{clip_id}-{tag}.mp4"


def srt_path(video: Path) -> Path:
    """Return the path of the SRT subtitles of the rendered clip video."""
    return video.with_suffix(".srt")


def metadata_path(video: Path) -> Path:
    """Return the path of the metadata JSON of the rendered clip video."""
    return video.with_suffix(".json")


def write_srt(work: Path, clip: Clip, fps: int) -> Path:
    """Write the SRT subtitles of clip, rendered at fps frames a second, next
    to its video and return their path (srt_path).

    The words come from work's transcript.json, as the render shows them.
    Raises StepError if transcript.json is missing or not valid, and
    ValueError if the clip has no rendered video or its caption template
    does not exist.
    """
    path = srt_path(rendered_video(clip))
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    template = get_template(clip.caption_template)
    words = rendered_words(transcript, clip, fps)
    write_text(path, build_srt(words, template.max_words_per_line))
    logger.info("wrote subtitles of clip %d to %s", clip.id, path)
    return path


def write_metadata(work: Path, clip: Clip, credit_template: str) -> Path:
    """Write the metadata JSON of clip next to its video and return its path
    (metadata_path).

    The credit line fills credit_template from work's meta.json. Raises
    StepError if meta.json is missing or not valid, and ValueError if the
    clip has no rendered video or credit_template is not valid.
    """
    path = metadata_path(rendered_video(clip))
    credit = credit_line(credit_template, load_meta(work))
    text = json.dumps(clip_metadata(clip, credit), ensure_ascii=False, indent=2)
    write_text(path, text + "\n")
    logger.info("wrote metadata of clip %d to %s", clip.id, path)
    return path


def write_zip(path: Path, files: Iterable[Path]) -> Path:
    """Write the zip archive path of files, each under its file name, in
    order, and return path.

    Videos (STORED_SUFFIXES) are stored, other files deflated. The archive
    goes to path.tmp first and is then renamed, so a reader never sees half
    of it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    try:
        with zipfile.ZipFile(tmp, "w") as archive:
            for file in files:
                stored = file.suffix in STORED_SUFFIXES
                method = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                archive.write(file, arcname=file.name, compress_type=method)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    return path
