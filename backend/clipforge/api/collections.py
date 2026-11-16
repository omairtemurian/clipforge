"""Collection endpoints (SPEC-v2 3.11): sets of clips from any projects, for
the owner and for agents (public API /api/v1 and MCP).

    GET    /collections                       -> [Collection]
    POST   /collections                       CollectionCreate ->
                                              CollectionDetail (201)
    GET    /collections/{id}                  -> CollectionDetail
    PATCH  /collections/{id}                  CollectionUpdate -> CollectionDetail
    DELETE /collections/{id}                  -> 204 (the clips stay)
    POST   /collections/{id}/items            CollectionAddClips ->
                                              CollectionDetail
    DELETE /collections/{id}/items/{clip_id}  -> CollectionDetail
    GET    /collections/{id}/download.zip     -> the zip of its rendered clips
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from sqlalchemy import Engine

from clipforge import clip_collections, collection_export
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.models import (
    Collection,
    CollectionAddClips,
    CollectionCreate,
    CollectionDetail,
    CollectionUpdate,
)

router = APIRouter()

EngineDep = Annotated[Engine, Depends(get_engine)]


@router.get("/collections")
def list_collections(engine: EngineDep) -> list[Collection]:
    """Return every collection, newest first, with its clip count."""
    return clip_collections.list_collections(engine)


@router.post("/collections", status_code=201)
def create_collection(body: CollectionCreate, engine: EngineDep) -> CollectionDetail:
    """Make an empty collection."""
    return clip_collections.create_collection(engine, body)


@router.get("/collections/{collection_id}")
def get_collection(collection_id: int, engine: EngineDep) -> CollectionDetail:
    """Return a collection with its clips in order; 404 if there is none."""
    try:
        return clip_collections.get_collection(engine, collection_id)
    except clip_collections.CollectionNotFound as exc:
        raise not_found("Collection", collection_id) from exc


@router.patch("/collections/{collection_id}")
def update_collection(
    collection_id: int, body: CollectionUpdate, engine: EngineDep
) -> CollectionDetail:
    """Rename a collection or change its description."""
    try:
        return clip_collections.update_collection(engine, collection_id, body)
    except clip_collections.CollectionNotFound as exc:
        raise not_found("Collection", collection_id) from exc


@router.delete("/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: int, engine: EngineDep) -> Response:
    """Delete a collection; its clips are not deleted."""
    try:
        clip_collections.delete_collection(engine, collection_id)
    except clip_collections.CollectionNotFound as exc:
        raise not_found("Collection", collection_id) from exc
    return Response(status_code=204)


@router.post("/collections/{collection_id}/items")
def add_collection_clips(
    collection_id: int, body: CollectionAddClips, engine: EngineDep
) -> CollectionDetail:
    """Add clips (from the gallery, a project's results or a search) to the
    end of a collection; clips in it already stay where they are. 404 if the
    collection or any clip does not exist (nothing is added)."""
    try:
        return clip_collections.add_clips(engine, collection_id, body.clip_ids)
    except clip_collections.CollectionNotFound as exc:
        raise not_found("Collection", collection_id) from exc
    except clip_collections.ClipsNotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc


@router.delete("/collections/{collection_id}/items/{clip_id}")
def remove_collection_clip(
    collection_id: int, clip_id: int, engine: EngineDep
) -> CollectionDetail:
    """Take a clip out of a collection; 404 if the collection does not exist
    or the clip is not in it."""
    try:
        return clip_collections.remove_clip(engine, collection_id, clip_id)
    except clip_collections.CollectionNotFound as exc:
        raise not_found("Collection", collection_id) from exc
    except clip_collections.ItemNotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc


@router.get("/collections/{collection_id}/download.zip")
def download_collection_zip(collection_id: int, engine: EngineDep) -> FileResponse:
    """Serve the zip of the collection's rendered clips and a manifest.json
    (collection_export); 409 if none of its clips is rendered."""
    try:
        path = collection_export.export_collection(engine, collection_id)
    except clip_collections.CollectionNotFound as exc:
        raise not_found("Collection", collection_id) from exc
    except collection_export.NothingToExport as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"clipforge-collection-{collection_id}.zip",
    )
