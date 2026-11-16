"""Tests of the brand vocabulary in the transcribe step (SPEC-v2 3.4): its
terms go to Whisper as hotwords and its corrections change the transcript.

A fake model records what faster-whisper would be called with; the signature
of the installed faster-whisper is checked, and a slow test runs the real
model with hotwords."""

import inspect
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from clipforge.config import Settings
from clipforge.models import ProcessingSettings, Transcript, Vocabulary
from clipforge.pipeline import transcribe
from clipforge.pipeline.step import AUDIO, StepError, StepSettings
from clipforge.pipeline.subtitle_import import save_subtitles
from clipforge.pipeline.transcribe import TRANSCRIPT, run
from clipforge.vocabulary import save_vocabulary
from test_transcribe import SOURCE, make_job, model_cfg  # noqa: F401


@dataclass
class FakeWord:
    word: str
    start: float
    end: float
    probability: float = 0.9


@dataclass
class FakeSegment:
    words: list[FakeWord]
    end: float


@dataclass
class FakeInfo:
    duration: float = 2.0
    language: str = "en"


class FakeModel:
    """Hears "we use open ai and cubernetes." and records the transcribe
    calls' keyword arguments."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def transcribe(
        self, audio: str, **kwargs: Any
    ) -> tuple[Iterator[FakeSegment], FakeInfo]:
        self.calls.append(kwargs)
        heard = [" we", " use", " open", " ai", " and", " Cuber", "netes."]
        words = [FakeWord(w, 0.2 * n, 0.2 * n + 0.15) for n, w in enumerate(heard)]
        return iter([FakeSegment(words, 1.4)]), FakeInfo()


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    fake = FakeModel()
    monkeypatch.setattr(transcribe, "load_model", lambda cfg: fake)
    return fake


def test_the_installed_faster_whisper_has_the_hotwords_parameter() -> None:
    from faster_whisper import WhisperModel

    parameters = inspect.signature(WhisperModel.transcribe).parameters
    assert parameters["hotwords"].default is None
    assert "initial_prompt" in parameters


def test_terms_are_the_hotwords_and_corrections_fix_the_transcript(
    tmp_path: Path, model: FakeModel
) -> None:
    cfg = Settings(data_dir=tmp_path / "data")
    save_vocabulary(
        Vocabulary(
            terms=["Kubernetes", "OpenAI"],
            corrections={"open ai": "OpenAI", "cubernetes": "Kubernetes"},
        ),
        cfg,
    )

    output = run(make_job(tmp_path / "job"), StepSettings(source=SOURCE, cfg=cfg))

    assert [call["hotwords"] for call in model.calls] == ["Kubernetes, OpenAI"]
    transcript = Transcript.model_validate_json(output.read_text())
    [segment] = transcript.segments
    assert segment.text == "we use OpenAI and Kubernetes."
    assert [w.text for w in segment.words] == [
        "we",
        "use",
        "OpenAI",
        "and",
        "Kubernetes.",
    ]
    assert (segment.words[2].start, segment.words[2].end) == (0.4, 0.75)
    assert (segment.words[4].start, segment.words[4].end) == (1.0, 1.35)


def test_without_a_vocabulary_whisper_gets_no_hotwords_and_nothing_changes(
    tmp_path: Path, model: FakeModel
) -> None:
    cfg = Settings(data_dir=tmp_path / "data")

    output = run(make_job(tmp_path / "job"), StepSettings(source=SOURCE, cfg=cfg))

    assert [call["hotwords"] for call in model.calls] == [None]
    [segment] = Transcript.model_validate_json(output.read_text()).segments
    assert segment.text == "we use open ai and Cubernetes."


def test_corrections_also_fix_the_transcript_of_uploaded_subtitles(
    tmp_path: Path,
) -> None:
    cfg = Settings(data_dir=tmp_path / "data")
    save_vocabulary(Vocabulary(corrections={"open ai": "OpenAI"}), cfg)
    token = save_subtitles(b"1\n00:00:00,500 --> 00:00:01,500\nuse open ai\n", cfg)
    processing = ProcessingSettings(subtitles_id=token)

    output = run(
        make_job(tmp_path / "job"),
        StepSettings(source=SOURCE, processing=processing, cfg=cfg),
    )

    [segment] = Transcript.model_validate_json(output.read_text()).segments
    assert segment.text == "use OpenAI"


def test_an_invalid_vocabulary_file_is_a_step_error(
    tmp_path: Path, model: FakeModel
) -> None:
    cfg = Settings(data_dir=tmp_path)
    (tmp_path / "vocabulary.json").write_text("not json")
    job = make_job(tmp_path / "job")

    with pytest.raises(StepError, match="is not a valid vocabulary"):
        run(job, StepSettings(source=SOURCE, cfg=cfg))

    assert model.calls == [] and not (job / TRANSCRIPT).exists()


@pytest.mark.slow
def test_the_real_model_accepts_hotwords(
    model_cfg: Settings,  # noqa: F811
    tmp_path: Path,
) -> None:
    job = make_job(tmp_path / "job")
    whisper = transcribe.load_model(model_cfg)

    words, language = transcribe._transcribe_chunk(
        whisper, job / AUDIO, "en", "Kubernetes, OpenAI", lambda done: None
    )

    assert words == [] and language == "en"
