"""The RNNoise model of ffmpeg's arnndn filter, used by speech enhancement
(pipeline/enhance) when it is downloaded: `beguiling-drafter` from
GregorR/rnnoise-models (trained on speech with noise from voice recordings;
the repo says its models carry no copyright), at a fixed commit and sha256.
"""

import logging
from pathlib import Path

import httpx

from clipforge.config import Settings
from clipforge.model_files import ModelFile, download_model_file

RNNOISE_DIRNAME = "rnnoise"
RNNOISE_MODEL = ModelFile(
    "bd.rnnn",
    "https://raw.githubusercontent.com/GregorR/rnnoise-models/"
    "3eee541a283fd3b8f81b85b1748e3b9ccbefa04d/"
    "beguiling-drafter-2018-08-30/bd.rnnn",
    "ae3f7411e1e6a884f839a4a145c394408398f09854dbc1216ee02faafc98a17b",
)

logger = logging.getLogger(__name__)


def rnnoise_model_path(cfg: Settings) -> Path:
    """Return the path of the RNNoise model in models_dir/rnnoise."""
    return cfg.models_dir / RNNOISE_DIRNAME / RNNOISE_MODEL.name


def download_rnnoise_model(
    cfg: Settings,
    *,
    force: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    """Download the RNNoise model into models_dir/rnnoise; return that
    directory. Nothing is fetched if the model is there already, unless
    force. transport, if given, carries the HTTP requests instead of the
    network. Raises like model_files.download_model_file."""
    path = rnnoise_model_path(cfg)
    if force or not path.is_file():
        download_model_file(RNNOISE_MODEL, path, transport)
    else:
        logger.info("%s is in %s", RNNOISE_MODEL.name, path.parent)
    return path.parent
