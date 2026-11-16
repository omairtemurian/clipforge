"""Stock B-roll providers (SPEC-v2 3.6): Pexels and Pixabay.

provider() returns the client of a provider, or raises ProviderDisabled with
the message that says which API key to set; provider_statuses() lists both
for the UI. download_clip() stores a found clip in the asset library with
its license and attribution.
"""

import httpx

from clipforge import config
from clipforge.config import Settings
from clipforge.models import StockProviderStatus, StockSource
from clipforge.stock import pexels, pixabay
from clipforge.stock.base import (
    ProviderDisabled,
    StockError,
    StockProvider,
    download_clip,
)

__all__ = [
    "ProviderDisabled",
    "StockError",
    "StockProvider",
    "download_clip",
    "provider",
    "provider_statuses",
]


def provider(
    name: StockSource,
    cfg: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> StockProvider:
    """Return the client of provider name with the keys of cfg (default: the
    app settings). Raises ProviderDisabled if its key is not set."""
    cfg = config.settings if cfg is None else cfg
    if name == "pexels":
        return pexels.PexelsClient(cfg.pexels_api_key, transport)
    return pixabay.PixabayClient(cfg.pixabay_api_key, transport)


def provider_statuses(cfg: Settings | None = None) -> list[StockProviderStatus]:
    """Return whether each provider is on; a provider without its key is
    disabled, with the message that says where to set it."""
    cfg = config.settings if cfg is None else cfg
    pexels_on, pixabay_on = bool(cfg.pexels_api_key), bool(cfg.pixabay_api_key)
    return [
        StockProviderStatus(
            provider="pexels",
            label=pexels.LABEL,
            enabled=pexels_on,
            message="" if pexels_on else pexels.disabled_message(),
        ),
        StockProviderStatus(
            provider="pixabay",
            label=pixabay.LABEL,
            enabled=pixabay_on,
            message="" if pixabay_on else pixabay.disabled_message(),
        ),
    ]
