"""The DeepFilterNet engine (SPEC-v2 3.5, engines/deepfilternet).

The install check, the program lookup, the arguments and the strength are
checked with a fake deep-filter (a shell script); the download with
httpx.MockTransport. The engine_deepfilternet tests run the real program
(`scripts/download_models.py --deepfilternet`) on the first 6 s of the
fixture's speech with white noise added, and measure the SNR against the
clean speech: 6.3 dB noisy, 22 dB enhanced at full strength.
"""

import hashlib
import stat
from pathlib import Path

import httpx
import numpy as np
import pytest
import soundfile
from clipforge import config
from clipforge.config import Settings
from clipforge.engines.deepfilternet import (
    MAX_ATTENUATION_DB,
    MIN_ATTENUATION_DB,
    RELEASES,
    DeepFilterError,
    DeepFilterNetEngine,
    attenuation_limit_db,
    bundled_binary_path,
    deep_filter_audio,
    deep_filter_binary,
    download_deep_filter,
    missing_message,
)
from clipforge.ffmpeg import ffprobe_json, run_ffmpeg
from clipforge.model_files import file_sha256
from clipforge.pipeline.enhance import enhance_speech

MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
CLIP_S = 6
NOISE = f"anoisesrc=a=0.03:c=white:r=48000:d={CLIP_S}:seed=1"
# The fake records its arguments and copies its input to <out dir>/in.wav
# (absolute tool paths: some tests empty PATH).
FAKE = """#!/bin/sh
if [ "$1" = "--version" ]; then echo "deep_filter 0.5.6"; exit 0; fi
echo "$@" > "{log}"
while [ $# -gt 1 ]; do
  if [ "$1" = "-o" ]; then out="$2"; fi
  shift
done
/bin/mkdir -p "$out" && /bin/cp "$1" "$out/in.wav"
"""


def write_script(path: Path, body: str) -> Path:
    """Write an executable shell script to path and return path."""
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    """A fake deep-filter program; it logs its arguments to <tmp>/args."""
    return write_script(tmp_path / "deep-filter", FAKE.format(log=tmp_path / "args"))


@pytest.fixture
def fake_cfg(tmp_path: Path, fake: Path) -> Settings:
    return Settings(models_dir=tmp_path / "models", deep_filter_bin=str(fake))


@pytest.fixture
def no_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings with no deep-filter anywhere (empty models_dir and PATH)."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    cfg = Settings(models_dir=tmp_path / "models", deep_filter_bin="")
    monkeypatch.setattr(config, "settings", cfg)
    return cfg


def test_the_strength_sets_the_attenuation_limit() -> None:
    assert attenuation_limit_db(0.0) == MIN_ATTENUATION_DB
    assert attenuation_limit_db(1.0) == MAX_ATTENUATION_DB
    assert attenuation_limit_db(0.25) < attenuation_limit_db(0.75)
    for wrong in (-0.1, 1.5):
        with pytest.raises(ValueError, match="between 0 and 1"):
            attenuation_limit_db(wrong)


def test_the_program_is_the_setting_then_the_download_then_path(
    tmp_path: Path, fake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    on_path = tmp_path / "bin"
    on_path.mkdir()
    write_script(on_path / "deep-filter", FAKE.format(log=tmp_path / "args"))
    monkeypatch.setenv("PATH", str(on_path))
    cfg = Settings(models_dir=tmp_path / "models", deep_filter_bin="")
    assert deep_filter_binary(cfg) == str(on_path / "deep-filter")

    bundled = bundled_binary_path(cfg)
    bundled.parent.mkdir(parents=True)
    write_script(bundled, FAKE)
    assert deep_filter_binary(cfg) == str(bundled)

    chosen = cfg.model_copy(update={"deep_filter_bin": str(fake)})
    assert deep_filter_binary(chosen) == str(fake)
    missing = cfg.model_copy(update={"deep_filter_bin": "clipforge-no-such-df"})
    assert deep_filter_binary(missing) is None


def test_install_check_reports_the_version_or_why_it_is_missing(
    tmp_path: Path, fake_cfg: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = DeepFilterNetEngine("deepfilternet", "DF")
    monkeypatch.setattr(config, "settings", fake_cfg)
    found = engine.install_check()
    assert (found.installed, found.version, found.error) == (True, "0.5.6", None)

    broken = write_script(tmp_path / "broken", "#!/bin/sh\necho boom >&2\nexit 3\n")
    monkeypatch.setattr(
        config, "settings", fake_cfg.model_copy(update={"deep_filter_bin": str(broken)})
    )
    failed = engine.install_check()
    assert not failed.installed
    assert "exited with 3: boom" in str(failed.error)


def test_install_check_without_the_program(no_program: Settings) -> None:
    missing = DeepFilterNetEngine("deepfilternet", "DF").install_check()
    assert not missing.installed
    assert missing.error == "deep-filter is not downloaded or on PATH"
    named = no_program.model_copy(update={"deep_filter_bin": "df-x"})
    assert missing_message(named) == "DEEP_FILTER_BIN df-x is not found"


def test_the_program_gets_48k_wav_delay_compensation_and_the_limit(
    tmp_path: Path, fake_cfg: Settings, sample_mp4: Path
) -> None:
    dst = tmp_path / "enhanced.wav"
    assert deep_filter_audio(sample_mp4, dst, 0.5, fake_cfg) == dst

    args = (tmp_path / "args").read_text().split()
    assert args[:3] == ["-D", "-a", f"{attenuation_limit_db(0.5):.1f}"]
    assert args[3] == "-o"
    stream = ffprobe_json(dst)["streams"][0]
    assert (stream["codec_name"], stream["sample_rate"]) == ("pcm_s16le", "48000")
    assert float(ffprobe_json(dst)["format"]["duration"]) == pytest.approx(60, abs=0.1)


def test_strength_zero_does_not_run_the_program(
    tmp_path: Path, fake_cfg: Settings, sample_mp4: Path
) -> None:
    dst = deep_filter_audio(sample_mp4, tmp_path / "copy.wav", 0.0, fake_cfg)
    assert dst.is_file()
    assert not (tmp_path / "args").exists()


def test_a_failing_or_missing_program_is_an_error(
    tmp_path: Path, sample_mp4: Path, no_program: Settings
) -> None:
    with pytest.raises(DeepFilterError, match="not downloaded or on PATH"):
        deep_filter_audio(sample_mp4, tmp_path / "x.wav", 0.5, no_program)
    broken = write_script(tmp_path / "broken", "#!/bin/sh\necho bad wav >&2\nexit 1\n")
    cfg = no_program.model_copy(update={"deep_filter_bin": str(broken)})
    with pytest.raises(DeepFilterError, match="exited with 1: bad wav"):
        deep_filter_audio(sample_mp4, tmp_path / "x.wav", 0.5, cfg)
    silent = write_script(tmp_path / "silent", "#!/bin/sh\nexit 0\n")
    cfg = no_program.model_copy(update={"deep_filter_bin": str(silent)})
    with pytest.raises(DeepFilterError, match="wrote no in.wav"):
        deep_filter_audio(sample_mp4, tmp_path / "x.wav", 0.5, cfg)


def test_enhance_speech_falls_back_to_ffmpeg(
    tmp_path: Path, sample_mp4: Path, no_program: Settings, fake_cfg: Settings
) -> None:
    clip = tmp_path / "clip.wav"
    run_ffmpeg(["-t", "2", "-i", sample_mp4, "-map", "0:a:0", clip])
    assert enhance_speech(clip, tmp_path / "ff.wav", 0.5, no_program) == "ffmpeg"
    assert (tmp_path / "ff.wav").is_file()
    assert enhance_speech(clip, tmp_path / "df.wav", 0.5, fake_cfg) == "deepfilternet"


def test_the_download_is_pinned_and_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"#!/bin/sh\necho 'deep_filter 0.5.6'\n"
    original = RELEASES["arm64"]
    release = original._replace(sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setitem(RELEASES, "arm64", release)
    cfg = Settings(models_dir=tmp_path / "models")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=payload)

    transport = httpx.MockTransport(handler)
    folder = download_deep_filter(cfg, transport=transport, machine="arm64")
    download_deep_filter(cfg, transport=transport, machine="arm64")
    binary = bundled_binary_path(cfg)
    assert folder == binary.parent
    assert seen == [original.url]
    assert binary.stat().st_mode & stat.S_IXUSR
    assert file_sha256(binary) == release.sha256


def test_a_download_with_another_sha256_is_refused(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path / "models")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"evil"))
    with pytest.raises(RuntimeError, match="sha256 is"):
        download_deep_filter(cfg, transport=transport, machine="arm64")
    assert not bundled_binary_path(cfg).exists()


def test_a_machine_without_a_release_binary_is_an_error(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path / "models")
    with pytest.raises(DeepFilterError, match="no deep-filter 0.5.6 release"):
        download_deep_filter(cfg, machine="riscv64")


# The real program.


def snr_db(clean: np.ndarray, audio: Path) -> float:
    """Return the SNR in dB of audio against the clean signal (same rate,
    aligned at 0; the shorter length is compared)."""
    signal, _ = soundfile.read(audio)
    n = min(len(clean), len(signal))
    noise = signal[:n] - clean[:n]
    return float(10 * np.log10(np.sum(clean[:n] ** 2) / np.sum(noise**2)))


@pytest.fixture(scope="module")
def speech(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[np.ndarray, Path]:
    """The clean first 6 s of the fixture's speech (48 kHz mono samples) and
    a WAV of it with white noise (amplitude 0.03) added."""
    folder = tmp_path_factory.mktemp("dfn")
    src = Path(__file__).resolve().parents[1] / "fixtures" / "sample.mp4"
    mono = "aresample=48000,pan=mono|c0=c0"
    clean_wav, noisy = folder / "clean.wav", folder / "noisy.wav"
    run_ffmpeg(
        ["-t", str(CLIP_S), "-i", src, "-af", mono, "-c:a", "pcm_s16le", clean_wav]
    )
    run_ffmpeg(
        [
            "-t",
            str(CLIP_S),
            "-i",
            src,
            "-f",
            "lavfi",
            "-i",
            NOISE,
            "-filter_complex",
            f"[0:a]{mono}[s];[s][1]amix=inputs=2:normalize=0",
            "-c:a",
            "pcm_s16le",
            noisy,
        ]
    )
    clean, _ = soundfile.read(clean_wav)
    return clean, noisy


@pytest.fixture(scope="module")
def real_cfg() -> Settings:
    return Settings(models_dir=MODELS_DIR)


@pytest.mark.engine_deepfilternet
def test_deepfilternet_improves_the_snr_of_noisy_speech(
    tmp_path: Path, speech: tuple[np.ndarray, Path], real_cfg: Settings
) -> None:
    clean, noisy = speech
    before = snr_db(clean, noisy)
    full = deep_filter_audio(noisy, tmp_path / "full.wav", 1.0, real_cfg)
    half = deep_filter_audio(noisy, tmp_path / "half.wav", 0.25, real_cfg)
    off = deep_filter_audio(noisy, tmp_path / "off.wav", 0.0, real_cfg)

    assert before == pytest.approx(6.3, abs=1.0)
    assert snr_db(clean, full) > before + 10
    assert before + 3 < snr_db(clean, half) < snr_db(clean, full)
    assert snr_db(clean, off) == pytest.approx(before, abs=0.1)


@pytest.mark.engine_deepfilternet
def test_enhance_speech_uses_the_installed_engine(
    tmp_path: Path, speech: tuple[np.ndarray, Path], real_cfg: Settings
) -> None:
    clean, noisy = speech
    dst = tmp_path / "enhanced.wav"
    assert enhance_speech(noisy, dst, 1.0, real_cfg) == "deepfilternet"
    assert snr_db(clean, dst) > snr_db(clean, noisy) + 10
