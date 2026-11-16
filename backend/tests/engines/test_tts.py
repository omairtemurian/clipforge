"""The voiceover engines (SPEC-v2 3.5, engines/tts and tts_files).

The install checks, the voices, the arguments of each engine and its errors
are checked with a fake piper program and a fake Kokoro model (tts_fakes);
the pinned downloads with httpx.MockTransport. The engine_kokoro and
engine_piper tests speak with the real engines and models
(`scripts/download_models.py --kokoro --piper`).
"""

import hashlib
import wave
from pathlib import Path

import httpx
import numpy as np
import pytest
from clipforge import config
from clipforge.config import Settings
from clipforge.engines import tts_files
from clipforge.engines.tts import (
    KokoroEngine,
    PiperEngine,
    TtsError,
    TtsNotInstalled,
    UnknownVoice,
    find_voice,
    installed_voices,
    kokoro_voices,
    piper_voices,
    synthesize,
    wav_seconds,
)
from clipforge.engines.tts_files import (
    KOKORO_LICENSE,
    PIPER_VOICE_FILES,
    UNKNOWN_LICENSE,
    download_kokoro,
    download_piper_voice,
    kokoro_paths,
    piper_dir,
)
from clipforge.model_files import ModelFile
from tts_fakes import (
    PIPER_MULTI,
    PIPER_VOICE,
    SECONDS_PER_CHAR,
    install_fake_kokoro,
    piper_runs,
    piper_settings,
)

MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
TEXT = "Hello there, this is the voiceover."


@pytest.fixture
def cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings (also config.settings) with the fake piper and its voices."""
    settings = piper_settings(tmp_path)
    monkeypatch.setattr(config, "settings", settings)
    return settings


def test_piper_voices_are_listed_one_per_speaker_with_their_license(
    cfg: Settings,
) -> None:
    voices = piper_voices(cfg)

    assert [(v.id, v.name, v.language, v.license) for v in voices] == [
        (f"piper:{PIPER_MULTI}:0", "group (en-GB, ann, low)", "en-GB", UNKNOWN_LICENSE),
        (f"piper:{PIPER_MULTI}:1", "group (en-GB, bob, low)", "en-GB", UNKNOWN_LICENSE),
        (f"piper:{PIPER_VOICE}", "test (en-US, medium)", "en-US", "CC0 (test)"),
    ]
    assert {(v.engine, v.gender) for v in voices} == {("piper", None)}


def test_piper_speaks_the_text_at_the_speed_and_speaker(cfg: Settings) -> None:
    out = cfg.models_dir.parent / "out.wav"

    seconds = synthesize(TEXT, f"piper:{PIPER_MULTI}:1", out, 1.25, cfg)

    model = piper_dir(cfg) / f"{PIPER_MULTI}.onnx"
    assert piper_runs(Path(cfg.piper_bin)) == [
        ["-m", str(model), "-c", f"{model}.json", "-f", str(out)]
        + ["--length-scale", "0.8000", "-s", "1"]
    ]
    assert seconds == pytest.approx(len(TEXT) * SECONDS_PER_CHAR * 0.8, abs=0.001)
    assert wav_seconds(out) == seconds


def test_a_failing_piper_is_an_engine_error(cfg: Settings) -> None:
    with pytest.raises(TtsError, match="piper exited with 1: piper: could not"):
        synthesize("FAIL now", f"piper:{PIPER_VOICE}", cfg.models_dir / "x.wav")


def test_unknown_voices_and_missing_engines_are_refused(
    cfg: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(UnknownVoice, match="no voice 'piper:nobody'"):
        find_voice("piper:nobody", cfg)
    with pytest.raises(UnknownVoice):
        find_voice("espeak:someone", cfg)
    with pytest.raises(TtsNotInstalled, match="kokoro is not installed"):
        find_voice("kokoro:af_heart", cfg)
    with pytest.raises(ValueError, match="speed 3"):
        synthesize(TEXT, f"piper:{PIPER_VOICE}", tmp_path / "x.wav", 3)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    no_program = cfg.model_copy(update={"piper_bin": ""})
    with pytest.raises(TtsNotInstalled, match="piper is not on PATH"):
        find_voice(f"piper:{PIPER_VOICE}", no_program)


def test_install_checks_say_what_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    empty = Settings(models_dir=tmp_path / "models", piper_bin="")
    monkeypatch.setattr(config, "settings", empty)
    piper = PiperEngine("piper", "Voiceover (Piper)").install_check()
    kokoro = KokoroEngine("kokoro", "Voiceover (Kokoro)").install_check()

    assert (piper.installed, piper.error) == (False, "piper is not on PATH")
    assert not kokoro.installed and kokoro.error is not None
    assert "kokoro-v1.0.onnx" in kokoro.error or "kokoro-onnx" in kokoro.error
    assert installed_voices() == []

    with_program = piper_settings(tmp_path / "p")
    (piper_dir(with_program) / f"{PIPER_VOICE}.onnx.json").unlink()
    (piper_dir(with_program) / f"{PIPER_MULTI}.onnx.json").unlink()
    monkeypatch.setattr(config, "settings", with_program)
    assert PiperEngine("piper", "x").install_check().error == (
        f"no Piper voice (.onnx + .onnx.json) in {piper_dir(with_program)}"
    )
    monkeypatch.setattr(config, "settings", piper_settings(tmp_path / "q"))
    assert PiperEngine("piper", "x").install_check().installed


def test_kokoro_lists_the_espeak_languages_and_speaks(
    cfg: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install_fake_kokoro(
        monkeypatch, cfg, ["af_heart", "bm_george", "jf_alpha", "zf_xiaoyi", "pm_alex"]
    )

    voices = kokoro_voices(cfg)
    seconds = synthesize(TEXT, "kokoro:bm_george", cfg.models_dir / "k.wav", 2.0)

    assert [(v.id, v.name, v.language, v.gender) for v in voices] == [
        ("kokoro:af_heart", "Heart (en-US)", "en-US", "female"),
        ("kokoro:bm_george", "George (en-GB)", "en-GB", "male"),
        ("kokoro:pm_alex", "Alex (pt-BR)", "pt-BR", "male"),
    ]
    assert {v.license for v in voices} == {KOKORO_LICENSE}
    assert installed_voices(cfg)[:3] == voices
    assert fake.calls == [
        {"text": TEXT, "voice": "bm_george", "speed": 2.0, "lang": "en-gb"}
    ]
    assert seconds == pytest.approx(len(TEXT) * SECONDS_PER_CHAR / 2, abs=0.001)
    with wave.open(str(cfg.models_dir / "k.wav")) as audio:
        assert (audio.getframerate(), audio.getsampwidth()) == (24000, 2)


def test_a_kokoro_failure_or_silence_is_an_engine_error(
    cfg: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_kokoro(monkeypatch, cfg, ["af_heart"])

    with pytest.raises(TtsError, match="Kokoro failed: IndexError"):
        synthesize("FAIL", "kokoro:af_heart", cfg.models_dir / "k.wav")
    with pytest.raises(TtsError, match="spoke nothing"):
        synthesize("  ", "kokoro:af_heart", cfg.models_dir / "k.wav", 2.0)


def test_a_file_that_is_not_a_wav_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "bad.wav").write_bytes(b"nope")
    with pytest.raises(TtsError, match="bad.wav is not a WAV file"):
        wav_seconds(tmp_path / "bad.wav")


def pinned(model: ModelFile, payload: bytes) -> ModelFile:
    """Return model pinned to the sha256 of payload."""
    return model._replace(sha256=hashlib.sha256(payload).hexdigest())


def test_the_downloads_are_pinned_and_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"model bytes"
    kokoro = (
        pinned(tts_files.KOKORO_MODEL, payload),
        pinned(tts_files.KOKORO_VOICES, payload),
    )
    monkeypatch.setattr(tts_files, "KOKORO_MODEL", kokoro[0])
    monkeypatch.setattr(tts_files, "KOKORO_VOICES", kokoro[1])
    piper = tuple(pinned(model, payload) for model in PIPER_VOICE_FILES)
    monkeypatch.setattr(tts_files, "PIPER_VOICE_FILES", piper)
    cfg = Settings(models_dir=tmp_path / "models")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=payload)

    transport = httpx.MockTransport(handler)
    for _ in range(2):
        assert download_kokoro(cfg, transport=transport) == kokoro_paths(cfg)[0].parent
        assert download_piper_voice(cfg, transport=transport) == piper_dir(cfg)

    assert seen == [model.url for model in (*kokoro, *piper)]
    assert all(path.read_bytes() == payload for path in kokoro_paths(cfg))
    names = sorted(path.name for path in piper_dir(cfg).iterdir())
    assert names == sorted(model.name for model in PIPER_VOICE_FILES)
    assert "/b4e358ffcb232591bf73a540e70f7de528e4174a/" in PIPER_VOICE_FILES[0].url
    download_piper_voice(cfg, force=True, transport=transport)
    assert len(seen) == 8


def test_a_download_with_another_sha256_is_refused(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path / "models")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"evil"))
    with pytest.raises(RuntimeError, match="sha256 is"):
        download_piper_voice(cfg, transport=transport)
    assert not any(piper_dir(cfg).iterdir())


@pytest.fixture
def real_cfg(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings that use the real models in models/."""
    settings = Settings(models_dir=MODELS_DIR)
    monkeypatch.setattr(config, "settings", settings)
    return settings


def loudness(path: Path) -> float:
    """Return the RMS of a 16-bit WAV, full scale 1."""
    with wave.open(str(path)) as audio:
        pcm = np.frombuffer(audio.readframes(audio.getnframes()), "<i2")
    return float(np.sqrt(np.mean((pcm / 32768.0) ** 2)))


@pytest.mark.engine_piper
def test_the_real_piper_voice_speaks_faster_when_asked(
    real_cfg: Settings, tmp_path: Path
) -> None:
    voice = f"piper:{tts_files.PIPER_DEFAULT_VOICE}"
    found = find_voice(voice)
    normal = synthesize(TEXT, voice, tmp_path / "1.wav", 1.0)
    fast = synthesize(TEXT, voice, tmp_path / "2.wav", 2.0)

    assert found.license == "public domain" and found.language == "en-US"
    # The silence after a sentence is not scaled, so twice as fast is not half.
    assert 1.5 < normal < 5 and normal * 0.5 < fast < normal * 0.7
    assert loudness(tmp_path / "1.wav") > 0.02


@pytest.mark.engine_kokoro
def test_the_real_kokoro_voices_speak_english_and_spanish(
    real_cfg: Settings, tmp_path: Path
) -> None:
    voices = {voice.id: voice for voice in kokoro_voices()}
    english = synthesize(TEXT, "kokoro:af_heart", tmp_path / "en.wav", 1.0)
    spanish = synthesize("Hola, ¿qué tal?", "kokoro:ef_dora", tmp_path / "es.wav")
    slow = synthesize(TEXT, "kokoro:af_heart", tmp_path / "slow.wav", 0.5)

    assert len(voices) >= 40 and voices["kokoro:ef_dora"].language == "es"
    assert 1.5 < english < 5 and 0.5 < spanish < 3
    assert slow == pytest.approx(english * 2, rel=0.2)
    assert loudness(tmp_path / "en.wav") > 0.02
    with wave.open(str(tmp_path / "en.wav")) as audio:
        assert audio.getframerate() == 24000
