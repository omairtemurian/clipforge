"""Tests of the transcribe step (SPEC 6.2).

The step's errors are tested without a model. The slow tests run the whisper
model that config.yaml names, which `make setup` downloads into models/;
they are skipped, saying so, when it is not there.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.model_files import missing_whisper_files, whisper_model_dir
from clipforge.models import ProcessingSettings, SourceMeta, Transcript
from clipforge.pipeline import ingest, transcribe
from clipforge.pipeline.step import (
    AUDIO,
    StepError,
    StepSettings,
    load_meta,
    load_step,
    write_json,
)
from clipforge.pipeline.subtitle_import import save_subtitles
from clipforge.pipeline.transcribe import TRANSCRIPT, run

MakeMedia = Callable[..., Path]
MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
H264_AAC = ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac")
SOURCE = "video.mp4"


@pytest.fixture(autouse=True)
def restore_hf_home(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the HF_HOME that loading a model sets (use_project_hf_home)."""
    monkeypatch.delenv("HF_HOME", raising=False)


@pytest.fixture
def model_cfg() -> Settings:
    """Settings that use the downloaded whisper model; skips if it is missing."""
    cfg = Settings(models_dir=MODELS_DIR, transcribe_backend="faster_whisper")
    model_dir = whisper_model_dir(cfg)
    if missing_whisper_files(model_dir):
        pytest.skip(
            f"whisper model {cfg.whisper_model!r} is not downloaded to "
            f"{model_dir}; run `make setup`"
        )
    return cfg


def make_job(job_dir: Path, duration: float = 2.0) -> Path:
    """Write the meta.json and audio.wav (a 440 Hz tone) that ingest writes."""
    job_dir.mkdir(parents=True)
    tone = f"sine=frequency=440:sample_rate=16000:duration={duration}"
    run_ffmpeg(["-f", "lavfi", "-i", tone, "-c:a", "pcm_s16le", job_dir / AUDIO])
    meta = SourceMeta(
        title="tone",
        duration=duration,
        width=320,
        height=240,
        fps=30.0,
        timeframe_start=0.0,
        timeframe_end=duration,
    )
    write_json(job_dir / "meta.json", meta)
    return job_dir


def test_transcribe_is_a_pipeline_step() -> None:
    assert load_step("transcribe") is run


def test_job_without_ingest_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(StepError, match="meta.json not found; run the ingest step"):
        run(tmp_path, StepSettings(source=SOURCE))


def test_missing_audio_is_an_error(tmp_path: Path) -> None:
    job = make_job(tmp_path / "job")
    (job / AUDIO).unlink()
    with pytest.raises(StepError, match="audio.wav not found; run the ingest step"):
        run(job, StepSettings(source=SOURCE))


def test_overlap_as_long_as_a_chunk_is_an_error(tmp_path: Path) -> None:
    cfg = Settings(chunk_minutes=1, chunk_overlap_s=60)
    with pytest.raises(StepError, match="cannot cut the audio into chunks: chunk"):
        run(make_job(tmp_path / "job"), StepSettings(source=SOURCE, cfg=cfg))


def test_missing_model_is_an_error_that_says_how_to_download_it(
    tmp_path: Path,
) -> None:
    job = make_job(tmp_path / "job")
    cfg = Settings(models_dir=tmp_path / "models", whisper_model="base")
    with pytest.raises(StepError) as error:
        run(job, StepSettings(source=SOURCE, cfg=cfg))
    model_dir = tmp_path / "models" / "whisper" / "base"
    assert f"{model_dir} lacks config.json, model.bin, tokenizer.json" in str(
        error.value
    )
    assert "scripts/download_models.py --whisper-model base" in str(error.value)
    assert not (job / TRANSCRIPT).exists()


def test_broken_model_is_an_error(tmp_path: Path) -> None:
    job = make_job(tmp_path / "job")
    cfg = Settings(models_dir=tmp_path / "models")
    model_dir = whisper_model_dir(cfg)
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")
    (model_dir / "tokenizer.json").write_text("{}")
    (model_dir / "model.bin").write_bytes(b"not a model")
    with pytest.raises(StepError, match="cannot load whisper model .* --force"):
        run(job, StepSettings(source=SOURCE, cfg=cfg))


def test_existing_transcript_is_kept_unless_forced(tmp_path: Path) -> None:
    job = make_job(tmp_path / "job")
    output = job / TRANSCRIPT
    output.write_text("old")
    progress: list[float] = []
    settings = StepSettings(
        source=SOURCE,
        cfg=Settings(models_dir=tmp_path / "models"),
        on_progress=progress.append,
    )
    assert run(job, settings) == output
    assert (output.read_text(), progress) == ("old", [1.0])
    # A forced run deletes the old transcript first, so a failure leaves none.
    with pytest.raises(StepError, match="is not downloaded"):
        run(job, settings, force=True)
    assert not output.exists()


@pytest.mark.slow
@pytest.mark.parametrize(
    "audio_source", ["sine=frequency=440", "anullsrc=channel_layout=mono"]
)
def test_speech_free_clip_gets_a_valid_transcript_without_words(
    model_cfg: Settings, make_media: MakeMedia, tmp_path: Path, audio_source: str
) -> None:
    """Whisper alone hears words such as "You" in silence; the VAD filter not."""
    name = f"{audio_source.partition('=')[0]}-5s.mp4"
    clip = make_media(name, *H264_AAC, audio_source=audio_source, duration=5.0)
    job = tmp_path / "job"
    ingest.run(job, StepSettings(source=str(clip)))
    progress: list[float] = []
    settings = StepSettings(
        source=str(clip), cfg=model_cfg, on_progress=progress.append
    )

    output = run(job, settings)

    assert output == job / TRANSCRIPT
    transcript = Transcript.model_validate_json(output.read_bytes(), strict=True)
    assert transcript.segments == []
    assert transcript.duration == load_meta(job).duration
    assert transcript.language.isalpha()
    assert progress == sorted(progress) and progress[-1] == 1.0
    assert [path.name for path in job.iterdir() if path.is_dir()] == []


def test_uploaded_subtitles_are_the_transcript_without_whisper(
    tmp_path: Path,
) -> None:
    cfg = Settings(data_dir=tmp_path / "data", models_dir=tmp_path / "models")
    token = save_subtitles(
        b"1\n00:00:00,500 --> 00:00:01,500\nHi there\n\n"
        b"2\n00:00:05,000 --> 00:00:06,000\nlater\n",
        cfg,
    )
    processing = ProcessingSettings(subtitles_id=token, language="fr")
    job = make_job(tmp_path / "job")

    # The whisper model is missing, so only the subtitles can transcribe it.
    transcript = Transcript.model_validate_json(
        run(
            job, StepSettings(source=SOURCE, processing=processing, cfg=cfg)
        ).read_text()
    )

    assert (transcript.language, transcript.approximate_times) == ("fr", True)
    [segment] = transcript.segments
    assert segment.text.strip() == "Hi there"
    assert [w.text.strip() for w in segment.words] == ["Hi", "there"]
    assert all(w.approximate for w in segment.words)
    assert (segment.start, segment.end) == (0.5, 1.5)


@pytest.mark.parametrize(
    "data",
    [
        b"1\n00:00:00,500 --> 00:00:01,500\nHi there\n",
        b"WEBVTT\n\n00:00.500 --> 00:01.500 align:start\nHi there\n",
    ],
    ids=["srt", "vtt"],
)
def test_the_step_log_says_transcription_was_skipped(
    data: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_whisper(cfg: Settings) -> None:
        raise AssertionError("whisper must not load when subtitles are given")

    monkeypatch.setattr(transcribe, "load_model", no_whisper)
    cfg = Settings(data_dir=tmp_path / "data")
    processing = ProcessingSettings(subtitles_id=save_subtitles(data, cfg))
    messages: list[str] = []
    monkeypatch.setattr(
        transcribe.logger,
        "info",
        lambda message, *args: messages.append(message % args),
    )

    output = run(
        make_job(tmp_path / "job"),
        StepSettings(source=SOURCE, processing=processing, cfg=cfg),
    )

    [skipped] = [m for m in messages if m.startswith("skipped transcription")]
    assert "read 1 segments from the uploaded subtitles" in skipped
    transcript = Transcript.model_validate_json(output.read_text())
    assert [w.text for w in transcript.segments[0].words] == ["Hi", "there"]


def test_subtitles_without_a_language_are_undetermined(tmp_path: Path) -> None:
    cfg = Settings(data_dir=tmp_path / "data")
    token = save_subtitles(b"00:00:00,000 --> 00:00:01,000\nHi\n", cfg)
    processing = ProcessingSettings(subtitles_id=token)

    output = run(
        make_job(tmp_path / "job"),
        StepSettings(source=SOURCE, processing=processing, cfg=cfg),
    )

    assert Transcript.model_validate_json(output.read_text()).language == "und"


@pytest.mark.parametrize(
    ("srt", "error"),
    [
        (None, "subtitles .* are missing"),
        (b"00:00:09,000 --> 00:00:10,000\nlate\n", "no subtitles inside"),
    ],
)
def test_unusable_subtitles_are_an_error(
    srt: bytes | None, error: str, tmp_path: Path
) -> None:
    cfg = Settings(data_dir=tmp_path / "data")
    token = "0" * 32 if srt is None else save_subtitles(srt, cfg)
    processing = ProcessingSettings(subtitles_id=token)
    with pytest.raises(StepError, match=error):
        run(
            make_job(tmp_path / "job"),
            StepSettings(source=SOURCE, processing=processing, cfg=cfg),
        )


def test_the_chosen_language_is_given_to_whisper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    languages: list[str | None] = []

    def fake_chunk(
        model: object,
        wav: Path,
        language: str | None,
        hotwords: str | None,
        report: object,
    ) -> tuple[list[object], str]:
        languages.append(language)
        return [], "en"

    monkeypatch.setattr(transcribe, "load_model", lambda cfg: object())
    monkeypatch.setattr(transcribe, "_transcribe_chunk", fake_chunk)
    job = make_job(tmp_path / "job")

    output = run(
        job,
        StepSettings(source=SOURCE, processing=ProcessingSettings(language="de")),
    )

    assert languages == ["de"]
    assert Transcript.model_validate_json(output.read_text()).language == "de"
