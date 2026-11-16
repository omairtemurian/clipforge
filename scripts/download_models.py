"""Download the ML models that ClipForge runs locally into models/.

`make setup` runs it. It downloads the whisper model (transcribe; on an Apple
Silicon Mac with mlx-whisper also its MLX version), YAMNet
(laugh and applause signals), the face, face landmark and person models
(reframe), the segmentation model (Pro Edit subject cut-out) and the RNNoise
model (speech enhancement); with --deepfilternet
also the deep-filter program of the optional DeepFilterNet engine (macOS),
with --kokoro the Kokoro voiceover model and voices and with --piper the
default Piper voice (the voiceover engines; engines/tts_files).
Models whose files are present are skipped, so it is safe to run again:

    uv run python scripts/download_models.py [--whisper-model NAME]
        [--deepfilternet] [--kokoro] [--piper] [--force]

Progress bars show when it runs in a terminal.
"""

import argparse
import logging
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from clipforge import config
from clipforge.engines.deepfilternet import download_deep_filter
from clipforge.engines.tts_files import download_kokoro, download_piper_voice
from clipforge.enhance_model import download_rnnoise_model
from clipforge.model_files import (
    download_face_model,
    download_whisper_model,
    download_yamnet_model,
)
from clipforge.pipeline.transcribe_mlx import (
    apple_silicon,
    download_mlx_model,
    mlx_installed,
    mlx_repo_id,
)
from clipforge.proedit.segment import download_segmenter


def main(argv: Sequence[str] | None = None) -> int:
    """Download the models; return 0, or 1 if a download fails."""
    parser = argparse.ArgumentParser(
        description="Download the models ClipForge runs locally into models/."
    )
    parser.add_argument(
        "--whisper-model",
        default=config.settings.whisper_model,
        help="faster-whisper model name or Hugging Face repo id "
        "(default: whisper_model from config.yaml, %(default)s)",
    )
    parser.add_argument(
        "--deepfilternet",
        action="store_true",
        help="also download the deep-filter program (DeepFilterNet engine, macOS)",
    )
    parser.add_argument(
        "--kokoro",
        action="store_true",
        help="also download the Kokoro voiceover model and voices (about 350 MB)",
    )
    parser.add_argument(
        "--piper",
        action="store_true",
        help="also download the default Piper voice, en_US-ljspeech-medium",
    )
    parser.add_argument(
        "--force", action="store_true", help="download again even if present"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(format="%(message)s")
    logging.getLogger("clipforge").setLevel(logging.INFO)

    cfg = config.settings.model_copy(update={"whisper_model": args.whisper_model})
    downloads: list[tuple[str, Callable[[], Path]]] = [
        (
            f"whisper model {args.whisper_model!r}",
            lambda: download_whisper_model(cfg, force=args.force),
        ),
        ("YAMNet model", lambda: download_yamnet_model(cfg, force=args.force)),
        ("face models", lambda: download_face_model(cfg, force=args.force)),
        (
            "segmentation model",
            lambda: download_segmenter(cfg, force=args.force),
        ),
        (
            "RNNoise model",
            lambda: download_rnnoise_model(cfg, force=args.force),
        ),
    ]
    if args.deepfilternet:
        downloads.append(
            (
                "DeepFilterNet program",
                lambda: download_deep_filter(cfg, force=args.force),
            )
        )
    if args.kokoro:
        downloads.append(
            ("Kokoro voiceover model", lambda: download_kokoro(cfg, force=args.force))
        )
    if args.piper:
        downloads.append(
            ("Piper voice", lambda: download_piper_voice(cfg, force=args.force))
        )
    if (
        cfg.transcribe_backend != "faster_whisper"
        and apple_silicon()
        and mlx_installed()
        and mlx_repo_id(args.whisper_model)
    ):
        downloads.insert(
            1,
            (
                f"MLX whisper model {args.whisper_model!r}",
                lambda: download_mlx_model(cfg, force=args.force),
            ),
        )
    for label, download in downloads:
        started = time.monotonic()
        try:
            path = download()
        except Exception as exc:  # report any download failure without a traceback
            print(
                f"download_models: {label}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        size_mb = sum(f.stat().st_size for f in path.iterdir() if f.is_file()) / 1e6
        elapsed = time.monotonic() - started
        print(f"{label}: {path} ({size_mb:.1f} MB, {elapsed:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
