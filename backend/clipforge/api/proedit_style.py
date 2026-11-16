"""Pro Edit style recipe endpoints (SPEC-v3 4), under /proedit.

A recipe is made from 1-5 links the owner pastes and the confirmation that
they may analyze them (an unchecked box is a 422). Analyzing downloads each
link (at most 3 min, 720p), measures its edit features and deletes the
media at once; only numbers are stored, then aggregated into the recipe's
targets with a short description. The recipe editor changes the name,
description and targets; a recipe is exported as JSON without media,
paths or links, and such a file is imported as a new recipe. The flag
proedit.enabled turns the endpoints off like the other Pro Edit endpoints.
"""

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.api.deps import get_engine, get_llm
from clipforge.api.errors import ApiError, not_found
from clipforge.api.proedit import require_proedit
from clipforge.llm import LLMClient
from clipforge.models import (
    StyleMetric,
    StyleRecipe,
    StyleRecipeExport,
    StyleRecipePatch,
    StyleTargets,
)
from clipforge.proedit.style import store
from clipforge.proedit.style.fetch import (
    MAX_HEIGHT,
    MAX_LINKS,
    MAX_SECONDS,
    RIGHTS_NOTICE,
    ReferenceBusy,
    validate_links,
)
from clipforge.proedit.style.metrics import METRICS
from clipforge.proedit.style.recipe import export_recipe, targets_of
from clipforge.proedit.style.store import ReferenceResult

router = APIRouter(prefix="/proedit", dependencies=[Depends(require_proedit)])

EngineDep = Annotated[Engine, Depends(get_engine)]
LLMDep = Annotated[LLMClient, Depends(get_llm)]


class StyleRecipeCreate(BaseModel):
    """A new recipe: its name, its reference links and the rights
    confirmation, which must be true."""

    name: str = Field(min_length=1, max_length=200)
    urls: list[str] = Field(min_length=1, max_length=MAX_LINKS)
    rights_confirmed: Literal[True]

    @field_validator("urls")
    @classmethod
    def _valid_links(cls, urls: list[str]) -> list[str]:
        return validate_links(urls)


class StyleRecipeDetail(BaseModel):
    """A recipe with its references and its targets."""

    recipe: StyleRecipe
    references: list[ReferenceResult]
    targets: StyleTargets


def _detail(
    recipe: StyleRecipe, references: list[ReferenceResult]
) -> StyleRecipeDetail:
    return StyleRecipeDetail(
        recipe=recipe, references=references, targets=targets_of(recipe)
    )


def _results(session: Session, recipe_id: int) -> list[ReferenceResult]:
    return [
        ReferenceResult(reference=ref)
        for ref in store.list_references(session, recipe_id)
    ]


class StyleTerms(BaseModel):
    """What the recipe form shows: the terms notice that goes with the
    rights checkbox and the limits of a reference."""

    notice: str
    max_links: int
    max_seconds: int
    max_height: int


@router.get("/style-recipes/terms")
def get_style_terms() -> StyleTerms:
    """Return the notice of the rights checkbox and the reference limits."""
    return StyleTerms(
        notice=RIGHTS_NOTICE,
        max_links=MAX_LINKS,
        max_seconds=MAX_SECONDS,
        max_height=MAX_HEIGHT,
    )


@router.get("/style-recipes/metrics")
def get_style_metrics() -> list[StyleMetric]:
    """Return the metrics of a recipe's targets, with their sliders."""
    return METRICS


@router.get("/style-recipes")
def list_style_recipes(engine: EngineDep) -> list[StyleRecipe]:
    """Return every style recipe, oldest first."""
    with Session(engine) as session:
        return store.list_recipes(session)


@router.post("/style-recipes", status_code=201)
def create_style_recipe(
    body: StyleRecipeCreate, engine: EngineDep
) -> StyleRecipeDetail:
    """Store a recipe with a reference per link and the rights confirmed
    now; nothing is downloaded yet. 422 without the confirmation, with no
    link or more than 5, or with a link that is not a supported video."""
    with Session(engine) as session:
        recipe = store.create_recipe(session, body.name, body.urls)
        return _detail(recipe, _results(session, recipe.id))


@router.post("/style-recipes/import", status_code=201)
def import_style_recipe(
    body: StyleRecipeExport, engine: EngineDep
) -> StyleRecipeDetail:
    """Store an exported recipe file as a new recipe without references.
    422 if it is not one (other fields, such as media or paths, are
    refused) or names an unknown metric."""
    with Session(engine) as session:
        try:
            recipe = store.import_recipe(session, body)
        except ValueError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        return _detail(recipe, [])


@router.get("/style-recipes/{recipe_id}")
def get_style_recipe(recipe_id: int, engine: EngineDep) -> StyleRecipeDetail:
    """Return recipe recipe_id with its references; 404 if it does not
    exist."""
    with Session(engine) as session:
        recipe = store.get_recipe(session, recipe_id)
        if recipe is None:
            raise not_found("style recipe", recipe_id)
        return _detail(recipe, _results(session, recipe_id))


@router.patch("/style-recipes/{recipe_id}")
def patch_style_recipe(
    recipe_id: int, body: StyleRecipePatch, engine: EngineDep
) -> StyleRecipeDetail:
    """Change the name, description or targets of recipe recipe_id (the
    recipe editor). 404 if it does not exist; 422 for a blank name or an
    unknown metric."""
    with Session(engine) as session:
        try:
            recipe = store.update_recipe(session, recipe_id, body)
        except ValueError as exc:
            raise ApiError(422, "validation_error", str(exc)) from exc
        if recipe is None:
            raise not_found("style recipe", recipe_id)
        return _detail(recipe, _results(session, recipe_id))


@router.get("/style-recipes/{recipe_id}/export")
def export_style_recipe(
    recipe_id: int, engine: EngineDep, response: Response
) -> StyleRecipeExport:
    """Return recipe recipe_id as a JSON file to download: name,
    description, reference count and targets, never media, paths or
    links. 404 if it does not exist."""
    with Session(engine) as session:
        recipe = store.get_recipe(session, recipe_id)
    if recipe is None:
        raise not_found("style recipe", recipe_id)
    slug = re.sub(r"[^a-z0-9]+", "-", recipe.name.lower()).strip("-") or "recipe"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{slug}.style-recipe.json"'
    )
    return export_recipe(recipe)


@router.post("/style-recipes/{recipe_id}/analyze")
def analyze_style_recipe(
    recipe_id: int, engine: EngineDep, llm: LLMDep
) -> StyleRecipeDetail:
    """Download and analyze each reference of recipe recipe_id that is not
    analyzed yet, deleting its media right after (also when it fails), and
    answer when all are done; when one was measured the targets are
    aggregated again and described by the LLM (rule-based text when it
    cannot be reached). A reference that cannot be analyzed (longer
    than 3 min, taller than 720p, unreachable) carries its reason in
    `error`. 404 if the recipe does not exist; 409 if one of its references
    is being analyzed already."""
    with Session(engine) as session:
        if store.get_recipe(session, recipe_id) is None:
            raise not_found("style recipe", recipe_id)
    try:
        results = store.analyze_recipe(engine, recipe_id, llm=llm)
    except ReferenceBusy as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    with Session(engine) as session:
        recipe = store.get_recipe(session, recipe_id)
    assert recipe is not None
    return _detail(recipe, results)
