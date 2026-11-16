"""The zip of a collection (SPEC-v2 3.9, 3.11): its rendered clips, each
with its SRT subtitles and metadata JSON if they were written, and a
manifest.json (models.CollectionManifest) that lists them in the
collection's order and says why any clip was left out.

The zip is {data_dir}/output/collections/{id}/collection.zip; videos are
named by the clip's id, which is unique across projects.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine

from clipforge import clip_collections, config
from clipforge.models import (
    CollectionManifest,
    CollectionManifestClip,
    CollectionManifestSkipped,
)
from clipforge.pipeline.export import metadata_path, srt_path, write_zip
from clipforge.pipeline.render import OUTPUT_DIRNAME
from clipforge.pipeline.step import write_json

logger = logging.getLogger(__name__)

COLLECTIONS_DIRNAME = "collections"
ZIP_NAME = "collection.zip"
MANIFEST_NAME = "manifest.json"


class NothingToExport(ValueError):
    """The collection has no clip with a rendered video."""


def collection_output(collection_id: int) -> Path:
    """Return the directory of a collection's exports:
    {data_dir}/output/collections/{collection_id}."""
    return (
        config.settings.data_dir
        / OUTPUT_DIRNAME
        / COLLECTIONS_DIRNAME
        / str(collection_id)
    )


def export_collection(engine: Engine, collection_id: int) -> Path:
    """Write the zip of collection collection_id and return its path.

    Raises clip_collections.CollectionNotFound if there is no such
    collection and NothingToExport if none of its clips has a rendered video
    on disk (the others are listed as skipped in the manifest).
    """
    collection = clip_collections.get_collection(engine, collection_id)
    clips: list[CollectionManifestClip] = []
    skipped: list[CollectionManifestSkipped] = []
    files: list[Path] = []
    for item in collection.items:
        detail = clip_collections.clip_of(engine, item.clip_id)
        video = Path(detail.output_path) if detail.output_path else None
        if detail.status != "rendered" or video is None or not video.is_file():
            reason = (
                "not rendered"
                if detail.status != "rendered"
                else "its rendered video is missing"
            )
            skipped.append(
                CollectionManifestSkipped(clip_id=item.clip_id, reason=reason)
            )
            logger.warning(
                "clip %d of collection %d: %s", item.clip_id, collection_id, reason
            )
            continue
        clips.append(
            CollectionManifestClip(
                clip_id=detail.id,
                project_id=detail.project_id,
                title=detail.title,
                hook_text=detail.hook_text,
                description=detail.description,
                hashtags=detail.hashtags,
                overall=detail.scores.overall,
                start=detail.start,
                end=detail.end,
                file=video.name,
            )
        )
        files += [
            file
            for file in (video, srt_path(video), metadata_path(video))
            if file.is_file()
        ]
    if not clips:
        raise NothingToExport(f"collection {collection_id} has no rendered clips")
    out = collection_output(collection_id)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / MANIFEST_NAME
    write_json(
        manifest,
        CollectionManifest(
            collection_id=collection_id,
            name=collection.name,
            description=collection.description,
            exported_at=datetime.now(UTC),
            clips=clips,
            skipped=skipped,
        ),
    )
    path = write_zip(out / ZIP_NAME, [*files, manifest])
    logger.info(
        "zipped %d clips of collection %d to %s", len(clips), collection_id, path
    )
    return path
