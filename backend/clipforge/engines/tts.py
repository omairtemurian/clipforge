"""The AI voiceover engines (SPEC-v2 3.5): local text-to-speech with Kokoro
or Piper, both checked on macOS arm64 (docs/progress.md, TASK-117).

Kokoro: the kokoro-onnx package (MIT; espeak-ng phonemes) runs Kokoro-82M
v1.0 in this process from models/kokoro (engines/tts_files). Its voice ids
start with a language letter and a gender letter ("af_heart": American
English, female); only the languages that espeak-ng speaks are listed
(KOKORO_LANGUAGES; Japanese and Mandarin need the misaki package).
`Kokoro.create(text, voice=, speed=, lang=)` returns float samples at 24 kHz;
speed is 0.5 to 2 (checked in kokoro_onnx 0.6.1's source).

Piper: the `piper` program of piper-tts 1.8 (GPL-3.0-or-later, run as a
separate program; PIPER_BIN or PATH) with the voices in models/piper.
`piper -m <voice.onnx> -c <voice.onnx.json> -f <out.wav> --length-scale <1/speed>
[-s <speaker>]` reads the text on stdin (flags from `piper --help`).

A voice id is "<engine>:<voice>" ("piper:<voice>:<speaker>" for one speaker
of a Piper voice with several). synthesize() writes a 16-bit PCM WAV.
"""

import importlib.metadata
import importlib.util
import shutil
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any, Literal

import numpy as np

from clipforge import config
from clipforge.config import Settings
from clipforge.engines.base import Engine, InstallStatus
from clipforge.engines.tts_files import (
    KOKORO_LICENSE,
    kokoro_paths,
    missing_kokoro_files,
    piper_config,
    piper_dir,
    piper_language,
    piper_license,
    piper_models,
)
from clipforge.models import TtsVoice

KOKORO_MODULE, KOKORO_PIP = "kokoro_onnx", "kokoro-onnx"
# Kokoro's language letters: (espeak-ng language, BCP 47 tag), as
# hexgrad/Kokoro-82M VOICES.md gives them.
KOKORO_LANGUAGES = {
    "a": ("en-us", "en-US"),
    "b": ("en-gb", "en-GB"),
    "e": ("es", "es"),
    "f": ("fr-fr", "fr-FR"),
    "h": ("hi", "hi"),
    "i": ("it", "it"),
    "p": ("pt-br", "pt-BR"),
}
GENDERS: dict[str, Literal["female", "male"]] = {"f": "female", "m": "male"}
PIPER_BINARY = "piper"
PIPER_TIMEOUT_S = 600.0

_kokoro_lock = threading.Lock()
_kokoro_models: dict[tuple[Path, Path], Any] = {}


class TtsError(RuntimeError):
    """A voice could not speak: the engine failed or wrote nothing."""


class UnknownVoice(TtsError):
    """No installed engine has the voice."""


class TtsNotInstalled(TtsError):
    """The engine of the voice is not installed; the message says why."""

    def __init__(self, engine: str, reason: str) -> None:
        super().__init__(f"voiceover engine {engine} is not installed: {reason}")
        self.engine = engine


def piper_binary(cfg: Settings | None = None) -> str | None:
    """Return the piper program: PIPER_BIN if set, else `piper` on PATH;
    None if it is not found."""
    cfg = cfg or config.settings
    return shutil.which(cfg.piper_bin or PIPER_BINARY)


def kokoro_problem(cfg: Settings | None = None) -> str | None:
    """Return why Kokoro cannot speak (package or files missing), or None."""
    cfg = cfg or config.settings
    if importlib.util.find_spec(KOKORO_MODULE) is None:
        return f"Python package {KOKORO_PIP} is not installed"
    missing = missing_kokoro_files(cfg)
    if missing:
        return f"Kokoro files missing in {kokoro_paths(cfg)[0].parent}: {missing}"
    return None


def piper_problem(cfg: Settings | None = None) -> str | None:
    """Return why Piper cannot speak (no program or no voice), or None."""
    cfg = cfg or config.settings
    if piper_binary(cfg) is None:
        return f"{cfg.piper_bin or PIPER_BINARY} is not on PATH"
    if not piper_models(cfg):
        return f"no Piper voice (.onnx + .onnx.json) in {piper_dir(cfg)}"
    return None


class KokoroEngine(Engine):
    """Installed when kokoro-onnx and the Kokoro files are there."""

    def install_check(self) -> InstallStatus:
        problem = kokoro_problem()
        if problem is not None:
            return InstallStatus(installed=False, error=problem)
        return InstallStatus(
            installed=True, version=importlib.metadata.version(KOKORO_PIP)
        )


class PiperEngine(Engine):
    """Installed when the piper program and at least one voice are there."""

    def install_check(self) -> InstallStatus:
        problem = piper_problem()
        if problem is not None:
            return InstallStatus(installed=False, error=problem)
        return InstallStatus(installed=True)


def kokoro_voices(cfg: Settings | None = None) -> list[TtsVoice]:
    """Return the voices of the Kokoro voices file that espeak-ng can speak,
    by id ([] if Kokoro is not installed)."""
    cfg = cfg or config.settings
    if kokoro_problem(cfg) is not None:
        return []
    with np.load(kokoro_paths(cfg)[1]) as styles:
        names = sorted(styles.files)
    voices = []
    for name in names:
        language = KOKORO_LANGUAGES.get(name[:1])
        if language is None or "_" not in name:
            continue
        voices.append(
            TtsVoice(
                id=f"kokoro:{name}",
                engine="kokoro",
                name=f"{name.split('_', 1)[1].title()} ({language[1]})",
                language=language[1],
                gender=GENDERS.get(name[1:2]),
                license=KOKORO_LICENSE,
            )
        )
    return voices


def piper_voices(cfg: Settings | None = None) -> list[TtsVoice]:
    """Return the voices in models/piper (one per speaker of a voice with
    several), by file name ([] if Piper is not installed)."""
    cfg = cfg or config.settings
    if piper_problem(cfg) is not None:
        return []
    voices = []
    for model in piper_models(cfg):
        info = piper_config(model)
        language = piper_language(model, info)
        quality = info.get("audio", {}).get("quality")
        label = f"{info.get('dataset') or model.stem} ({language}"
        tail = f", {quality})" if quality else ")"
        speakers = info.get("speaker_id_map") or {}
        if int(info.get("num_speakers", 1)) > 1 and speakers:
            named = [
                (f"{model.stem}:{number}", f"{label}, {speaker}{tail}")
                for speaker, number in sorted(speakers.items(), key=lambda p: p[1])
            ]
        else:
            named = [(model.stem, f"{label}{tail}")]
        voices += [
            TtsVoice(
                id=f"piper:{key}",
                engine="piper",
                name=name,
                language=language,
                gender=None,
                license=piper_license(model),
            )
            for key, name in named
        ]
    return voices


def installed_voices(cfg: Settings | None = None) -> list[TtsVoice]:
    """Return the voices of every installed voiceover engine (Kokoro first)."""
    return kokoro_voices(cfg) + piper_voices(cfg)


def find_voice(voice_id: str, cfg: Settings | None = None) -> TtsVoice:
    """Return the installed voice voice_id. Raises TtsNotInstalled if its
    engine is not installed and UnknownVoice if no engine has it."""
    cfg = cfg or config.settings
    engine = voice_id.split(":", 1)[0]
    problems: dict[str, Any] = {"kokoro": kokoro_problem, "piper": piper_problem}
    if engine in problems and (problem := problems[engine](cfg)) is not None:
        raise TtsNotInstalled(engine, problem)
    found = next((v for v in installed_voices(cfg) if v.id == voice_id), None)
    if found is None:
        raise UnknownVoice(f"there is no voice {voice_id!r}")
    return found


def synthesize(
    text: str, voice_id: str, dst: Path, speed: float = 1.0, cfg: Settings | None = None
) -> float:
    """Write text spoken by voice voice_id at speed (0.5 to 2) to dst, a
    16-bit PCM WAV, and return its length in seconds. Raises like
    find_voice, ValueError for a speed outside 0.5 to 2 and TtsError if the
    engine fails or speaks nothing."""
    if not 0.5 <= speed <= 2.0:
        raise ValueError(f"speed {speed} is not between 0.5 and 2")
    cfg = cfg or config.settings
    voice = find_voice(voice_id, cfg)
    name = voice_id.split(":", 1)[1]
    if voice.engine == "kokoro":
        _kokoro_say(text, name, speed, dst, cfg)
    else:
        _piper_say(text, name, speed, dst, cfg)
    seconds = wav_seconds(dst)
    if seconds <= 0:
        raise TtsError(f"{voice.engine} spoke nothing for {text!r}")
    return seconds


def wav_seconds(path: Path) -> float:
    """Return the length in seconds of a PCM WAV file (TtsError if it is not
    one)."""
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    except (OSError, EOFError, wave.Error) as exc:
        raise TtsError(f"{path.name} is not a WAV file: {exc}") from exc


def _kokoro_say(text: str, name: str, speed: float, dst: Path, cfg: Settings) -> None:
    """Speak text with Kokoro voice name into dst (the model is loaded once
    and runs one text at a time)."""
    paths = kokoro_paths(cfg)
    with _kokoro_lock:
        model = _kokoro_models.get(paths)
        if model is None:
            from kokoro_onnx import Kokoro

            model = _kokoro_models[paths] = Kokoro(str(paths[0]), str(paths[1]))
        try:
            samples, rate = model.create(
                text, voice=name, speed=speed, lang=KOKORO_LANGUAGES[name[:1]][0]
            )
        except Exception as exc:  # the package raises many kinds of errors
            raise TtsError(f"Kokoro failed: {type(exc).__name__}: {exc}") from exc
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype("<i2")
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(int(rate))
        out.writeframes(pcm.tobytes())


def _piper_say(text: str, name: str, speed: float, dst: Path, cfg: Settings) -> None:
    """Speak text with Piper voice name ("<voice>" or "<voice>:<speaker>")
    into dst."""
    stem, _, speaker = name.partition(":")
    model = piper_dir(cfg) / f"{stem}.onnx"
    binary = piper_binary(cfg)
    assert binary is not None
    command = [binary, "-m", str(model), "-c", f"{model}.json", "-f", str(dst)]
    command += ["--length-scale", f"{1 / speed:.4f}"]
    if speaker:
        command += ["-s", speaker]
    try:
        subprocess.run(
            command,
            input=text.encode(),
            check=True,
            capture_output=True,
            timeout=PIPER_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as exc:
        lines = exc.stderr.decode(errors="replace").strip().splitlines()
        raise TtsError(
            f"piper exited with {exc.returncode}: {lines[-1] if lines else ''}"
        ) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TtsError(f"piper: {exc}") from exc
