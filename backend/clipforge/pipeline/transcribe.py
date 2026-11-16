"""Transcribe step (SPEC 6.2): write the speech of the job's video to transcript.json.

The audio of the project's timeframe is cut with ffmpeg (-ss/-t) into chunks
of chunk_minutes that overlap by chunk_overlap_s, and Whisper transcribes
each chunk with word timestamps: faster-whisper on the CPU, or MLX Whisper
on the Apple GPU (transcribe_backend; see transcribe_mlx). The chunks' words
are moved to source time, every word of an overlap is kept once, and the
words are grouped into sentence segments (see transcript_merge).

The brand vocabulary (clipforge.vocabulary) takes part twice: its terms are
Whisper's hotwords, and its corrections are applied to the transcript
afterwards, to an uploaded subtitles' transcript too.

Every word gets speaker S0. Diarization (optional in SPEC 2, with HF_TOKEN)
would need pyannote, which ClipForge does not install.
"""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from clipforge.config import Settings
from clipforge.ffmpeg import extract_audio_wav
from clipforge.model_files import (
    missing_whisper_files,
    use_project_hf_home,
    whisper_model_dir,
)
from clipforge.models import SourceMeta, Transcript, Vocabulary
from clipforge.pipeline.step import (
    AUDIO,
    TRANSCRIPT,
    StepError,
    StepSettings,
    is_done,
    load_meta,
    write_json,
)
from clipforge.pipeline.subtitle_import import (
    SubtitlesError,
    cue_words,
    parse_subtitles,
    subtitles_path,
)
from clipforge.pipeline.transcribe_mlx import (
    MlxWhisper,
    active_backend,
    load_mlx_model,
)
from clipforge.pipeline.transcript_correct import correct_transcript
from clipforge.pipeline.transcript_merge import (
    SPEAKER,
    Chunk,
    TimedWord,
    build_transcript,
    merge_chunks,
    plan_chunks,
)
from clipforge.vocabulary import VocabularyError, hotwords_text, load_vocabulary

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

CHUNK_WAV = "chunk.wav"
# Int8 weights on the CPU (SPEC 2); CTranslate2 runs them as int8_float32.
DEVICE = "auto"
COMPUTE_TYPE = "int8"
# The language of a transcript from subtitles when the user did not say.
UNKNOWN_LANGUAGE = "und"

logger = logging.getLogger(__name__)


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Transcribe the timeframe of job_dir/audio.wav into transcript.json.

    Reads meta.json and audio.wav, which ingest wrote. The language is
    settings.processing.language, or if unset detected in the first chunk
    with speech and kept for the chunks after it. With
    settings.processing.subtitles_id set, the uploaded SRT or VTT is the
    transcript instead (srt_transcript) and the transcription is skipped:
    Whisper does not load or run.
    Skips the work if transcript.json exists, unless force. Raises StepError
    if ingest has not run, the timeframe cannot be split into chunks, or the
    whisper model is missing or broken, and FFmpegError if ffmpeg fails.
    """
    output = job_dir / TRANSCRIPT
    if is_done(output, force=force):
        logger.info("%s exists; skipping transcribe", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    vocabulary = _vocabulary(settings.cfg)
    subtitles = settings.processing.subtitles_id
    if subtitles is not None:
        transcript = _corrected(srt_transcript(subtitles, settings, meta), vocabulary)
        write_json(output, transcript)
        settings.report_progress(1.0)
        logger.info(
            "skipped transcription: read %d segments from the uploaded "
            "subtitles %s into %s",
            len(transcript.segments),
            subtitles,
            output,
        )
        return output
    audio = job_dir / AUDIO
    if not audio.is_file():
        raise StepError(f"{audio} not found; run the ingest step first")
    cfg = settings.cfg
    try:
        chunks = plan_chunks(
            meta.timeframe_start,
            meta.timeframe_end,
            cfg.chunk_minutes * 60,
            cfg.chunk_overlap_s,
        )
    except ValueError as exc:
        raise StepError(f"cannot cut the audio into chunks: {exc}") from exc
    model = load_model(cfg)
    if cfg.hf_token:
        logger.warning(
            "HF_TOKEN is set, but diarization needs pyannote, which is not "
            "installed; every word gets speaker %s",
            SPEAKER,
        )

    heard: list[tuple[Chunk, list[TimedWord]]] = []
    language = settings.processing.language
    first_detected = ""
    with tempfile.TemporaryDirectory(prefix="transcribe-", dir=job_dir) as tmp:
        wav = Path(tmp) / CHUNK_WAV
        for index, chunk in enumerate(chunks):
            logger.info(
                "transcribing chunk %d/%d (%.1fs-%.1fs)",
                index + 1,
                len(chunks),
                chunk.start,
                chunk.end,
            )
            extract_audio_wav(
                audio, wav, start=chunk.start, duration=chunk.end - chunk.start
            )
            words, detected = _transcribe_chunk(
                model,
                wav,
                language,
                hotwords_text(vocabulary),
                _chunk_progress(settings, index, len(chunks)),
            )
            if language is None and words:
                language = detected
            first_detected = first_detected or detected
            heard.append((chunk, words))

    transcript = _corrected(
        build_transcript(
            merge_chunks(heard),
            language=language or first_detected,
            duration=meta.duration,
        ),
        vocabulary,
    )
    write_json(output, transcript)
    settings.report_progress(1.0)
    logger.info(
        "transcribed %d words in %d segments (language %s) into %s",
        sum(len(segment.words) for segment in transcript.segments),
        len(transcript.segments),
        transcript.language,
        output,
    )
    return output


def _vocabulary(cfg: Settings) -> Vocabulary:
    """Return the brand vocabulary saved under cfg's data directory; raises
    StepError if its file is not valid."""
    try:
        return load_vocabulary(cfg)
    except VocabularyError as exc:
        raise StepError(str(exc)) from exc


def _corrected(transcript: Transcript, vocabulary: Vocabulary) -> Transcript:
    """Return transcript with the vocabulary's corrections applied."""
    fixed, count = correct_transcript(transcript, vocabulary.corrections)
    if count:
        logger.info("vocabulary: corrected %d places in the transcript", count)
    return fixed


def srt_transcript(token: str, settings: StepSettings, meta: SourceMeta) -> Transcript:
    """Return the transcript of the uploaded SRT or VTT with token over meta's
    timeframe, with approximate word times (subtitle_import.cue_words). Its
    language is settings.processing.language, or "und" if unset. Raises
    StepError if the file is missing or not valid.
    """
    path = subtitles_path(token, settings.cfg)
    try:
        cues = parse_subtitles(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StepError(f"the uploaded subtitles {path} are missing") from exc
    except SubtitlesError as exc:
        raise StepError(f"{path} is not valid subtitles: {exc}") from exc
    words = cue_words(cues, meta.timeframe_start, meta.timeframe_end)
    if not words:
        raise StepError(f"{path} has no subtitles inside the timeframe")
    transcript = build_transcript(
        words,
        language=settings.processing.language or UNKNOWN_LANGUAGE,
        duration=meta.duration,
    )
    return transcript.model_copy(update={"approximate_times": True})


def load_model(cfg: Settings) -> "WhisperModel | MlxWhisper":
    """Load the whisper model cfg.whisper_model from cfg.models_dir, for the
    backend that transcribe_mlx.active_backend picks: MLX on the Apple GPU,
    or faster-whisper on the CPU.

    The model is not downloaded here (scripts/download_models.py does that),
    so transcription never touches the network. Raises StepError if the
    model's files are missing or cannot be loaded.
    """
    if active_backend(cfg) == "mlx":
        logger.info("transcribing on the Apple GPU with MLX Whisper")
        return load_mlx_model(cfg)
    model_dir = whisper_model_dir(cfg)
    missing = missing_whisper_files(model_dir)
    if missing:
        raise StepError(
            f"whisper model {cfg.whisper_model!r} is not downloaded: {model_dir} "
            f"lacks {', '.join(missing)}; run `uv run python "
            f"scripts/download_models.py --whisper-model {cfg.whisper_model}`"
        )
    use_project_hf_home(cfg)
    from faster_whisper import WhisperModel

    try:
        return WhisperModel(str(model_dir), device=DEVICE, compute_type=COMPUTE_TYPE)
    except (RuntimeError, ValueError, OSError) as exc:
        raise StepError(
            f"cannot load whisper model {cfg.whisper_model!r} from {model_dir}: "
            f"{exc}; download it again with scripts/download_models.py --force"
        ) from exc


def _transcribe_chunk(
    model: "WhisperModel | MlxWhisper",
    wav: Path,
    language: str | None,
    hotwords: str | None,
    on_progress: Callable[[float], None],
) -> tuple[list[TimedWord], str]:
    """Transcribe the chunk in wav and return its words and language.

    Times are relative to the chunk. language None lets Whisper detect it.
    hotwords, if set, are the terms that Whisper's decoder is primed with
    in every window (faster-whisper's hotwords parameter).
    The voice activity filter skips audio without speech, where Whisper
    would otherwise make up words (MLX drops a silence of 2 s or more that
    Whisper filled). on_progress gets the fraction of the
    chunk done after each Whisper segment (MLX: once, at the end).
    """
    if isinstance(model, MlxWhisper):
        return model.transcribe_chunk(wav, language, hotwords, on_progress)
    segments, info = model.transcribe(
        str(wav),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        hotwords=hotwords,
    )
    words: list[TimedWord] = []
    for segment in segments:
        last = len(segment.words) - 1
        words += [
            TimedWord(
                text=word.word,
                start=float(word.start),
                end=float(word.end),
                prob=float(word.probability),
                segment_end=index == last,
            )
            for index, word in enumerate(segment.words)
        ]
        on_progress(segment.end / info.duration if info.duration > 0 else 1.0)
    return words, str(info.language)


def _chunk_progress(
    settings: StepSettings, index: int, count: int
) -> Callable[[float], None]:
    """Return a callback that reports the step's progress within chunk index."""

    def report(done: float) -> None:
        settings.report_progress((index + min(done, 1.0)) / count)

    return report
