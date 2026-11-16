"""Download a recommended CC0-only starter set of sound effects from Freesound
(SPEC-v3 5.5). Needs FREESOUND_API_KEY in .env.local (a free key at
https://freesound.org/apiv2/apply); nothing is downloaded at install time.

    uv run --project backend python scripts/fetch_starter_sfx.py
        [--licenses assets/sfx/starter/LICENSES.md]

The sounds (previews) go to data/audio/freesound/ and the asset library,
tagged and categorized; only the table of licenses that this writes may be
committed, never the audio. Safe to run again: sounds that are in the
library are not downloaded twice.
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from clipforge import config
from clipforge.db import init_db
from clipforge.proedit.audio.freesound import FreesoundClient, disabled_message
from clipforge.proedit.audio.starter import build_starter_set, licenses_markdown
from clipforge.stock.base import ProviderDisabled, StockError
from sqlmodel import Session

DEFAULT_LICENSES = (
    Path(__file__).resolve().parents[1] / "assets/sfx/starter/LICENSES.md"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Build the starter set; return 0, or 1 without a Freesound key or if
    Freesound cannot be searched."""
    parser = argparse.ArgumentParser(
        description="Download a CC0 starter set of sound effects from Freesound."
    )
    parser.add_argument(
        "--licenses",
        type=Path,
        default=DEFAULT_LICENSES,
        help="where to write the table of licenses (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(format="%(message)s")
    logging.getLogger("clipforge").setLevel(logging.INFO)
    try:
        client = FreesoundClient(config.settings.freesound_api_key)
    except ProviderDisabled:
        print(disabled_message(), file=sys.stderr)
        return 1
    engine = init_db()
    try:
        with Session(engine) as session:
            sounds = build_starter_set(client, session)
    except StockError as exc:
        print(f"Starter set failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    args.licenses.parent.mkdir(parents=True, exist_ok=True)
    args.licenses.write_text(licenses_markdown(sounds), encoding="utf-8")
    print(f"{len(sounds)} sounds in the library; licenses in {args.licenses}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
