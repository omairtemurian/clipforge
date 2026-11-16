"""Fakes of the voiceover engines (engines/tts) for tests that must not need
them installed: a fake `piper` program and a fake Kokoro model.

The fake piper logs its arguments (one JSON list per run) and writes a
22050 Hz 16-bit WAV of a 440 Hz tone, SECONDS_PER_CHAR of the stripped text
times --length-scale long; text with "FAIL" in it makes it exit 1. The fake
Kokoro model speaks the same way at 24 kHz, 1/speed as long.
"""

import json
import stat
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from clipforge.config import Settings
from clipforge.engines import tts
from clipforge.engines.tts_files import kokoro_paths

SECONDS_PER_CHAR = 0.05
PIPER_VOICE = "en_US-test-medium"
PIPER_MULTI = "en_GB-group-low"
CARD = "# Model card\n\n* License: CC0 (test)\n"

FAKE_PIPER = """#!{python}
import json, math, struct, sys, wave
args = sys.argv[1:]
with open({log!r}, "a") as log:
    log.write(json.dumps(args) + "\\n")
opts = dict(zip(args[::2], args[1::2]))
text = sys.stdin.read()
if "FAIL" in text:
    print("piper: could not speak", file=sys.stderr)
    sys.exit(1)
rate = 22050
frames = int(rate * {per_char} * len(text.strip()) * float(opts["--length-scale"]))
pcm = b"".join(
    struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * n / rate)))
    for n in range(frames)
)
with wave.open(opts["-f"], "wb") as out:
    out.setnchannels(1)
    out.setsampwidth(2)
    out.setframerate(rate)
    out.writeframes(pcm)
"""


def write_fake_piper(folder: Path) -> Path:
    """Write the fake piper to folder/piper (its log: folder/piper.log)."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "piper"
    path.write_text(
        FAKE_PIPER.format(
            python=sys.executable,
            log=str(folder / "piper.log"),
            per_char=SECONDS_PER_CHAR,
        )
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def piper_runs(fake: Path) -> list[list[str]]:
    """Return the arguments of each run of the fake piper."""
    log = fake.with_name("piper.log")
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def add_piper_voice(
    models_dir: Path, name: str, config: dict[str, Any], card: str | None = CARD
) -> None:
    """Put a Piper voice called name (a dummy model) in models_dir/piper."""
    folder = models_dir / "piper"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.onnx").write_bytes(b"onnx")
    (folder / f"{name}.onnx.json").write_text(json.dumps(config))
    if card is not None:
        (folder / f"{name}.MODEL_CARD").write_text(card)


def piper_settings(tmp_path: Path, **changes: Any) -> Settings:
    """Settings whose piper is the fake, with voice PIPER_VOICE (one
    speaker) and PIPER_MULTI (two), and no Kokoro."""
    models = tmp_path / "models"
    add_piper_voice(
        models,
        PIPER_VOICE,
        {
            "dataset": "test",
            "language": {"code": "en_US"},
            "audio": {"quality": "medium"},
        },
    )
    add_piper_voice(
        models,
        PIPER_MULTI,
        {
            "dataset": "group",
            "language": {"code": "en_GB"},
            "audio": {"quality": "low"},
            "num_speakers": 2,
            "speaker_id_map": {"bob": 1, "ann": 0},
        },
        card=None,
    )
    fake = write_fake_piper(tmp_path / "bin")
    return Settings(models_dir=models, piper_bin=str(fake), **changes)


class FakeKokoro:
    """A Kokoro model that speaks a tone; it keeps what it was asked."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(
        self, text: str, voice: str, speed: float, lang: str
    ) -> tuple[np.ndarray, int]:
        self.calls.append({"text": text, "voice": voice, "speed": speed, "lang": lang})
        if "FAIL" in text:
            raise IndexError("phonemes out of range")
        rate = 24000
        frames = int(rate * SECONDS_PER_CHAR * len(text.strip()) / speed)
        samples = 0.3 * np.sin(2 * np.pi * 440 * np.arange(frames) / rate)
        return samples.astype(np.float32), rate


def install_fake_kokoro(
    monkeypatch: pytest.MonkeyPatch, cfg: Settings, voices: list[str]
) -> FakeKokoro:
    """Make Kokoro look installed for cfg with the given voices, speaking
    with a FakeKokoro (returned)."""
    model_path, voices_path = kokoro_paths(cfg)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"onnx")
    with voices_path.open("wb") as file:
        np.savez(file, **{name: np.zeros((2, 256), np.float32) for name in voices})
    fake = FakeKokoro()
    monkeypatch.setitem(tts._kokoro_models, (model_path, voices_path), fake)
    monkeypatch.setattr(tts, "kokoro_problem", lambda cfg=None: None, raising=True)
    return fake
