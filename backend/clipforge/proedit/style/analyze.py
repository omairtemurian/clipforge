"""All the features of a style reference (SPEC-v3 4.3): its video features
(analyze_video), captions (analyze_captions, None without tesseract or
captions), audio (analyze_audio with the YAMNet model of the signals step,
None without an audio stream) and structure (analyze_structure).
"""

from pathlib import Path

from clipforge import config
from clipforge.config import Settings
from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.pipeline.step import StepError
from clipforge.pipeline.yamnet import load_yamnet
from clipforge.proedit.style.analyze_audio import AudioFeatures, analyze_audio
from clipforge.proedit.style.analyze_captions import CaptionFeatures, analyze_captions
from clipforge.proedit.style.analyze_structure import (
    StructureFeatures,
    analyze_structure,
)
from clipforge.proedit.style.analyze_video import ReferenceVideoFeatures, analyze_video


class ReferenceFeatures(ReferenceVideoFeatures):
    """The features of a reference: its video features plus its captions,
    audio and structure."""

    captions: CaptionFeatures | None = None
    audio: AudioFeatures | None = None
    structure: StructureFeatures


def analyze_reference_media(
    path: Path, cfg: Settings | None = None
) -> ReferenceFeatures:
    """Return the features of the reference video at path (module doc); the
    YAMNet model comes from cfg (config.settings by default) and is loaded
    only for a video with audio.

    Raises StepError if the video cannot be read or the model is missing.
    """
    try:
        info = probe_media(path)
    except FFmpegError as exc:
        raise StepError(f"cannot read {path}: {exc}") from exc
    video = analyze_video(path)
    audio = (
        analyze_audio(path, load_yamnet(cfg or config.settings))
        if info.audio_codec
        else None
    )
    return ReferenceFeatures(
        video=video.video,
        rhythm=video.rhythm,
        motion=video.motion,
        look=video.look,
        glitches=video.glitches,
        captions=analyze_captions(path),
        audio=audio,
        structure=analyze_structure(path, video, audio),
    )
