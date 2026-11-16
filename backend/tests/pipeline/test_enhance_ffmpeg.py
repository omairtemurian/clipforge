"""Tests of speech enhancement with ffmpeg's filters (SPEC-v2 3.5,
pipeline/enhance): the filters exist in the installed ffmpeg, strength sets
their parameters, and on a noisy recording (a tone for speech, then noise
alone) the RMS level of the noise floor (astats) falls with strength while
the speech stays. arnndn runs with the real RNNoise model if `make setup`
downloaded it; the download itself is checked with httpx.MockTransport."""

import hashlib
import re
from pathlib import Path

import httpx
import pytest
from clipforge import enhance_model
from clipforge.config import Settings
from clipforge.enhance_model import (
    RNNOISE_MODEL,
    download_rnnoise_model,
    rnnoise_model_path,
)
from clipforge.ffmpeg import FFmpegError, run_ffmpeg
from clipforge.pipeline.enhance import (
    enhance_audio,
    enhance_filter,
    measure_noise_floor,
)

MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
# The recording: a 220 Hz tone ("speech") for 1.5 s, white noise all 3 s.
SPEECH = (0.2, 1.0)
NOISE_ONLY = (2.0, 0.9)
NOISE_FLOOR_DB = -35.4
TONE = "aevalsrc=0.3*sin(2*PI*220*t)*lt(t\\,1.5):d=3:s=16000"
NOISE = "anoisesrc=a=0.03:c=white:d=3:r=16000:seed=1"
STRENGTHS = [0.25, 0.5, 0.75, 1.0]


def rms_db(audio: Path, window: tuple[float, float]) -> float:
    """Return the RMS level in dBFS of audio from window[0] for window[1]
    seconds, as astats measures it."""
    start, length = window
    stderr = run_ffmpeg(
        [
            "-ss",
            f"{start}",
            "-t",
            f"{length}",
            "-i",
            audio,
            "-map",
            "0:a:0",
            "-af",
            "astats=measure_perchannel=none:measure_overall=RMS_level",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"RMS level dB: (\S+)", stderr)[-1])


@pytest.fixture(scope="module")
def noisy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 3 s 16 kHz mono WAV: a 0.3-amplitude 220 Hz tone for 1.5 s, and
    white noise (amplitude 0.03, about -35 dBFS RMS) over all of it."""
    path = tmp_path_factory.mktemp("enhance") / "noisy.wav"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            TONE,
            "-f",
            "lavfi",
            "-i",
            NOISE,
            "-filter_complex",
            "[0][1]amix=inputs=2:normalize=0",
            path,
        ]
    )
    return path


@pytest.fixture
def no_model_cfg(tmp_path: Path) -> Settings:
    """Settings whose models_dir has no RNNoise model: afftdn alone."""
    return Settings(models_dir=tmp_path / "models")


@pytest.fixture(scope="module")
def rnnoise_cfg() -> Settings:
    """Settings that use the downloaded RNNoise model; skips if it is missing."""
    cfg = Settings(models_dir=MODELS_DIR)
    if not rnnoise_model_path(cfg).is_file():
        pytest.skip(
            f"the RNNoise model is not in {rnnoise_model_path(cfg)}; make setup"
        )
    return cfg


def parameter(audio_filter: str, name: str) -> float:
    """Return the number the filter string gives to the option name."""
    return float(re.search(rf"\b{name}=(-?[\d.]+)", audio_filter).group(1))  # type: ignore[union-attr]


def test_the_filters_exist_in_the_installed_ffmpeg() -> None:
    filters = run_ffmpeg(["-filters"], loglevel="error").stdout.decode().split("\n")
    names = {parts[1] for line in filters if len(parts := line.split()) > 1}

    assert {"afftdn", "arnndn", "highpass"} <= names


def test_the_options_the_filters_are_given_exist(noisy: Path, tmp_path: Path) -> None:
    for model in (None, MODELS_DIR / "rnnoise" / RNNOISE_MODEL.name):
        if model is not None and not model.is_file():
            continue
        graph = enhance_filter(0.5, -40.0, model)
        out = tmp_path / "graph.wav"

        run_ffmpeg(["-i", noisy, "-af", graph, out])

        assert out.stat().st_size > 0


def test_strength_zero_is_no_filter_and_outside_0_to_1_is_an_error() -> None:
    assert enhance_filter(0.0, -40.0) == ""
    for strength in (-0.1, 1.1):
        with pytest.raises(ValueError, match="between 0 and 1"):
            enhance_filter(strength, -40.0)


def test_strength_sets_the_reduction_and_the_residual_floor() -> None:
    graphs = [enhance_filter(s, -40.0) for s in (0.01, *STRENGTHS)]

    reductions = [parameter(g, "nr") for g in graphs]
    residuals = [parameter(g, "rf") for g in graphs]
    assert reductions == sorted(reductions)
    assert residuals == sorted(residuals, reverse=True)
    assert reductions[0] == pytest.approx(6.2)
    assert reductions[-1] == 30.0
    assert [parameter(g, "nf") for g in graphs] == [-34.0] * 5
    assert residuals[-1] == -54.0
    assert graphs[-1].startswith("highpass=f=80,afftdn=")


def test_the_noise_floor_and_the_residual_floor_stay_in_afftdns_range() -> None:
    loud = enhance_filter(1.0, -5.0)
    silent = enhance_filter(1.0, float("-inf"))

    assert parameter(loud, "nf") == -20.0
    assert parameter(silent, "nf") == -80.0
    assert parameter(silent, "rf") == -80.0


def test_arnndn_is_added_with_the_model_escaped_and_strength_as_its_mix() -> None:
    graph = enhance_filter(0.5, -40.0, Path("/m/it's here.rnnn"))

    assert graph.startswith("highpass=f=80,arnndn=m=")
    assert "mix=0.50" in graph
    assert ",afftdn=" in graph
    assert "it's here" not in graph  # the quote is escaped, not left bare


def test_the_noise_floor_is_the_quietest_stretch_of_the_recording(
    noisy: Path,
) -> None:
    assert measure_noise_floor(noisy) == pytest.approx(NOISE_FLOOR_DB, abs=2.0)


def test_a_file_without_sound_has_no_noise_floor(tmp_path: Path) -> None:
    video = tmp_path / "silent.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1", video])

    with pytest.raises(FFmpegError):
        measure_noise_floor(video)


def test_the_noise_floor_falls_with_strength_and_the_speech_stays(
    noisy: Path, tmp_path: Path, no_model_cfg: Settings
) -> None:
    before = rms_db(noisy, NOISE_ONLY)
    speech_before = rms_db(noisy, SPEECH)
    floors = []
    for strength in STRENGTHS:
        out = enhance_audio(
            noisy, tmp_path / f"s{strength}.wav", strength, no_model_cfg
        )
        floors.append(rms_db(out, NOISE_ONLY))
        assert rms_db(out, SPEECH) == pytest.approx(speech_before, abs=3.0)

    assert before == pytest.approx(NOISE_FLOOR_DB, abs=2.0)
    assert floors == sorted(floors, reverse=True)
    assert floors[0] < before - 8
    assert floors[-1] < before - 25


def test_strength_zero_leaves_the_sound_as_it_was(
    noisy: Path, tmp_path: Path, no_model_cfg: Settings
) -> None:
    out = enhance_audio(noisy, tmp_path / "zero.wav", 0.0, no_model_cfg)

    assert rms_db(out, NOISE_ONLY) == pytest.approx(rms_db(noisy, NOISE_ONLY), abs=0.2)


def test_the_sound_of_a_video_is_enhanced(
    noisy: Path, tmp_path: Path, no_model_cfg: Settings
) -> None:
    video = tmp_path / "talk.mp4"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x64:rate=10:duration=3",
            "-i",
            noisy,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            video,
        ]
    )

    out = enhance_audio(video, tmp_path / "talk.wav", 1.0, no_model_cfg)

    assert rms_db(out, NOISE_ONLY) < rms_db(video, NOISE_ONLY) - 20


def test_arnndn_with_the_real_model_lowers_the_noise_floor_too(
    noisy: Path, tmp_path: Path, rnnoise_cfg: Settings
) -> None:
    out = enhance_audio(noisy, tmp_path / "rnn.wav", 1.0, rnnoise_cfg)

    assert rms_db(out, NOISE_ONLY) < rms_db(noisy, NOISE_ONLY) - 25


def test_the_rnnoise_model_is_downloaded_once_from_its_pinned_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"rnnoise-nu model file version 1"
    pinned = RNNOISE_MODEL._replace(sha256=hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(enhance_model, "RNNOISE_MODEL", pinned)
    cfg = Settings(models_dir=tmp_path / "models")
    urls: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(answer)
    directory = download_rnnoise_model(cfg, transport=transport)
    download_rnnoise_model(cfg, transport=transport)

    assert directory == cfg.models_dir / "rnnoise"
    assert (directory / "bd.rnnn").read_bytes() == body
    assert urls == [RNNOISE_MODEL.url]
    assert "3eee541a283fd3b8f81b85b1748e3b9ccbefa04d" in RNNOISE_MODEL.url


def test_a_model_with_another_sha256_is_refused_and_not_kept(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path / "models")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"other"))

    with pytest.raises(RuntimeError, match="sha256"):
        download_rnnoise_model(cfg, transport=transport)

    assert not rnnoise_model_path(cfg).exists()
    assert not list(rnnoise_model_path(cfg).parent.glob("*.part"))
