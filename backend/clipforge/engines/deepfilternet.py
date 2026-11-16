"""The DeepFilterNet speech enhancement engine (SPEC-v2 3.5): the official
`deep-filter` command line program of DeepFilterNet 0.5.6 (Rust, MIT or
Apache-2.0), which carries the DeepFilterNet3 model and needs no Python
packages. The pip package `deepfilternet` 0.5.6 cannot share this project's
environment: it pins numpy<2 and imports `torchaudio.backend`, gone since
torchaudio 2.1 (docs/questions.md "TASK-113").

The program is DEEP_FILTER_BIN if set, else models/deepfilternet/deep-filter
(`scripts/download_models.py --deepfilternet` puts the release binary of this
machine there, sha256-pinned), else `deep-filter` on PATH.

`deep-filter [-D] [-a <dB>] -o <dir> <in.wav>` writes <dir>/<in.wav>. The
model runs at 48 kHz, so the sound is resampled to a 48 kHz WAV first; -D
compensates the STFT and lookahead delay (without it the output lags) and
`-a` limits the attenuation (0 dB: nothing removed, 100 dB: no limit), which
the strength slider sets. Flags checked with `deep-filter --help` (0.5.6).
"""

import platform
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import httpx

from clipforge import config
from clipforge.config import Settings
from clipforge.engines.base import Engine, InstallStatus
from clipforge.ffmpeg import run_ffmpeg
from clipforge.model_files import ModelFile, download_model_file

DIRNAME = "deepfilternet"
BINARY_NAME = "deep-filter"
VERSION = "0.5.6"
SAMPLE_RATE = 48_000
MIN_ATTENUATION_DB = 6.0
# deep-filter's attenuation limit at which nothing is held back.
MAX_ATTENUATION_DB = 100.0
VERSION_TIMEOUT_S = 30.0
RUN_TIMEOUT_S = 1800.0
_RELEASES = f"https://github.com/Rikorose/DeepFilterNet/releases/download/v{VERSION}/"
# The release binaries for macOS, by `platform.machine()`; sha256 computed
# from the downloads (the release publishes no digests).
RELEASES: dict[str, ModelFile] = {
    "arm64": ModelFile(
        BINARY_NAME,
        f"{_RELEASES}deep-filter-{VERSION}-aarch64-apple-darwin",
        "4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081",
    ),
    "x86_64": ModelFile(
        BINARY_NAME,
        f"{_RELEASES}deep-filter-{VERSION}-x86_64-apple-darwin",
        "d3be84003acb7c23e738ad7f70a158ec779a8d233a82e7fa3e717d112eb5b50f",
    ),
}
_VERSION = re.compile(r"deep_filter (\S+)")


class DeepFilterError(RuntimeError):
    """deep-filter is missing, failed or wrote no output."""


def bundled_binary_path(cfg: Settings) -> Path:
    """Return where the download puts deep-filter: models_dir/deepfilternet."""
    return cfg.models_dir / DIRNAME / BINARY_NAME


def deep_filter_binary(cfg: Settings | None = None) -> str | None:
    """Return the deep-filter program to run: DEEP_FILTER_BIN if set, else
    the downloaded one if it is there, else `deep-filter` from PATH; None if
    there is none."""
    cfg = cfg or config.settings
    if cfg.deep_filter_bin:
        return shutil.which(cfg.deep_filter_bin)
    bundled = bundled_binary_path(cfg)
    if bundled.is_file():
        return str(bundled)
    return shutil.which(BINARY_NAME)


def missing_message(cfg: Settings | None = None) -> str:
    """Why no deep-filter program is found (DEEP_FILTER_BIN or the default)."""
    cfg = cfg or config.settings
    if cfg.deep_filter_bin:
        return f"DEEP_FILTER_BIN {cfg.deep_filter_bin} is not found"
    return f"{BINARY_NAME} is not downloaded or on PATH"


def deep_filter_version(binary: str) -> str:
    """Return the version `<binary> --version` prints ("deep_filter 0.5.6").
    Raises DeepFilterError if it cannot run, fails or prints something else."""
    stdout = _run([binary, "--version"], VERSION_TIMEOUT_S).stdout.decode()
    found = _VERSION.search(stdout)
    if found is None:
        raise DeepFilterError(f"{binary} --version printed {stdout.strip()!r}")
    return found.group(1)


class DeepFilterNetEngine(Engine):
    """Installed when the deep-filter program is found and prints its version."""

    def install_check(self) -> InstallStatus:
        binary = deep_filter_binary()
        if binary is None:
            return InstallStatus(installed=False, error=missing_message())
        try:
            return InstallStatus(installed=True, version=deep_filter_version(binary))
        except DeepFilterError as exc:
            return InstallStatus(installed=False, error=str(exc))


def download_deep_filter(
    cfg: Settings,
    *,
    force: bool = False,
    transport: httpx.BaseTransport | None = None,
    machine: str | None = None,
) -> Path:
    """Download the deep-filter release binary of this Mac (or of machine,
    a `platform.machine()` name) into models_dir/deepfilternet, executable;
    return that directory. Nothing is fetched if it is there already, unless
    force. Raises DeepFilterError for a machine without a release binary,
    and like model_files.download_model_file if the download fails."""
    if machine is None:
        machine = platform.machine() if platform.system() == "Darwin" else ""
    release = RELEASES.get(machine)
    if release is None:
        raise DeepFilterError(
            f"no deep-filter {VERSION} release binary for {platform.system()} "
            f"{platform.machine()}; put {BINARY_NAME} on PATH or set DEEP_FILTER_BIN"
        )
    path = bundled_binary_path(cfg)
    if force or not path.is_file():
        download_model_file(release, path, transport)
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path.parent


def attenuation_limit_db(strength: float) -> float:
    """Return deep-filter's attenuation limit for strength (0 to 1 above 0):
    6 dB at the weakest, no limit (100 dB) at 1. Raises ValueError if
    strength is outside 0 to 1."""
    if not 0.0 <= strength <= 1.0:
        raise ValueError(f"enhancement strength {strength} is not between 0 and 1")
    return MIN_ATTENUATION_DB + (MAX_ATTENUATION_DB - MIN_ATTENUATION_DB) * strength


def deep_filter_audio(
    src: Path, dst: Path, strength: float, cfg: Settings | None = None
) -> Path:
    """Write the sound of src (audio or video file) enhanced by DeepFilterNet
    at strength (0 to 1; 0 copies it) to dst, a 48 kHz 16-bit PCM WAV, and
    return dst. Raises ValueError if strength is outside 0 to 1,
    DeepFilterError if deep-filter is missing or fails and FFmpegError if
    ffmpeg cannot read src."""
    limit = attenuation_limit_db(strength)
    binary = deep_filter_binary(cfg)
    if binary is None:
        raise DeepFilterError(missing_message(cfg))
    with tempfile.TemporaryDirectory(prefix="clipforge-dfn-") as work:
        wav = Path(work) / "in.wav"
        run_ffmpeg(
            [
                "-i",
                src,
                "-map",
                "0:a:0",
                "-ar",
                str(SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                wav,
            ]
        )
        if strength == 0.0:
            shutil.copyfile(wav, dst)
            return dst
        out_dir = Path(work) / "out"
        _run(
            [binary, "-D", "-a", f"{limit:.1f}", "-o", str(out_dir), str(wav)],
            RUN_TIMEOUT_S,
        )
        enhanced = out_dir / wav.name
        if not enhanced.is_file():
            raise DeepFilterError(f"{binary} wrote no {enhanced.name} in {out_dir}")
        shutil.copyfile(enhanced, dst)
    return dst


def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
    """Run command; raise DeepFilterError with its stderr if it fails."""
    try:
        return subprocess.run(command, check=True, capture_output=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode(errors="replace").strip()
        raise DeepFilterError(
            f"{command[0]} exited with {exc.returncode}: {message}"
        ) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeepFilterError(f"{command[0]}: {exc}") from exc
