"""The stored side of style learning (SPEC-v3 4.1, 4.2, 6): creating a style
recipe with its references and analyzing the ones not analyzed yet.

A recipe is stored with its links only after the owner confirmed the
rights. Analyzing a reference fetches it (fetch.analyze_reference), measures
its edit features and stores them as numbers under
features["references"][<reference id>]; the media is deleted by then, and
deleted_at records it, also when the analysis failed. When an analysis
measured a new reference, the recipe's targets (features["targets"]) and
description are made again from all its references (style/recipe), which
replaces edits made in the recipe editor.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.config import Settings
from clipforge.llm import LLMClient
from clipforge.models import (
    StyleRecipe,
    StyleRecipeExport,
    StyleRecipePatch,
    StyleReference,
)
from clipforge.pipeline.step import StepError
from clipforge.proedit.rows import StyleRecipeRow, StyleReferenceRow
from clipforge.proedit.style.analyze import analyze_reference_media
from clipforge.proedit.style.fetch import (
    ReferenceBusy,
    analyze_reference,
    validate_links,
)
from clipforge.proedit.style.recipe import aggregate, check_targets, describe

Analyzer = Callable[[Path], dict[str, Any]]


class ReferenceResult(BaseModel):
    """A reference after an analysis run: its row and the reason it could
    not be analyzed (None when it was)."""

    reference: StyleReference
    error: str | None = None


def measure_features(path: Path, cfg: Settings | None = None) -> dict[str, Any]:
    """Return the numeric edit features of the reference video at path
    (analyze.analyze_reference_media: what the shared extractors measured,
    cut rhythm against its beats, zoom/shake summaries, vignette/grain,
    glitches, captions, audio and structure) as JSON data; cfg gives the
    YAMNet model (config.settings by default)."""
    return analyze_reference_media(path, cfg).model_dump(mode="json")


def create_recipe(
    session: Session, name: str, urls: list[str], now: datetime | None = None
) -> StyleRecipe:
    """Store a recipe called name with one reference per link of urls, the
    rights confirmed now. Raises ValueError if the links are not valid
    (fetch.validate_links)."""
    links = validate_links(urls)
    confirmed = now or datetime.now(UTC)
    recipe = StyleRecipeRow(name=name.strip(), created_at=confirmed)
    session.add(recipe)
    session.flush()
    assert recipe.id is not None
    for link in links:
        session.add(
            StyleReferenceRow(
                recipe_id=recipe.id, url=link, rights_confirmed_at=confirmed
            )
        )
    session.commit()
    session.refresh(recipe)
    return recipe.to_model()


def get_recipe(session: Session, recipe_id: int) -> StyleRecipe | None:
    """Return recipe recipe_id, or None if there is none."""
    row = session.get(StyleRecipeRow, recipe_id)
    return row.to_model() if row else None


def list_recipes(session: Session) -> list[StyleRecipe]:
    """Return every recipe, oldest first."""
    rows = session.exec(select(StyleRecipeRow).order_by(col(StyleRecipeRow.id)))
    return [row.to_model() for row in rows]


def list_references(session: Session, recipe_id: int) -> list[StyleReference]:
    """Return the references of recipe recipe_id in the order of its links."""
    rows = session.exec(
        select(StyleReferenceRow)
        .where(StyleReferenceRow.recipe_id == recipe_id)
        .order_by(col(StyleReferenceRow.id))
    )
    return [row.to_model() for row in rows]


def analyze_recipe(
    engine: Engine,
    recipe_id: int,
    analyzer: Analyzer = measure_features,
    llm: LLMClient | None = None,
) -> list[ReferenceResult]:
    """Analyze each reference of recipe recipe_id that is not analyzed yet,
    one after the other, and return one result per reference; when one was
    measured, aggregate the targets again and have llm describe them
    (rule-based text without it).

    A reference that cannot be fetched or measured (StepError) keeps
    analyzed_at empty and carries the reason; the others go on. No database
    session is open while a video downloads. Raises ReferenceBusy if a
    reference is being analyzed by another call.
    """
    with Session(engine) as session:
        pending = [
            (ref.id, ref.url)
            for ref in list_references(session, recipe_id)
            if ref.analyzed_at is None
        ]
    errors: dict[int, str] = {}
    for reference_id, url in pending:
        try:
            features = analyze_reference(url, reference_id, analyzer)
        except ReferenceBusy:
            raise
        except StepError as exc:
            errors[reference_id] = str(exc)
            _record(engine, recipe_id, reference_id, None)
        else:
            _record(engine, recipe_id, reference_id, features)
    if len(errors) < len(pending):
        refresh_targets(engine, recipe_id, llm)
    with Session(engine) as session:
        return [
            ReferenceResult(reference=ref, error=errors.get(ref.id))
            for ref in list_references(session, recipe_id)
        ]


def _record(
    engine: Engine,
    recipe_id: int,
    reference_id: int,
    features: dict[str, Any] | None,
) -> None:
    """Store that the media of a reference is deleted and, with features,
    that it was analyzed and what it measured."""
    now = datetime.now(UTC)
    with Session(engine) as session:
        reference = session.get(StyleReferenceRow, reference_id)
        recipe = session.get(StyleRecipeRow, recipe_id)
        if reference is None or recipe is None:
            return
        reference.deleted_at = now
        if features is not None:
            reference.analyzed_at = now
            recipe.features = {
                **recipe.features,
                "references": {
                    **recipe.features.get("references", {}),
                    str(reference_id): features,
                },
            }
            recipe.reference_count = len(recipe.features["references"])
        session.commit()


def refresh_targets(engine: Engine, recipe_id: int, llm: LLMClient | None) -> None:
    """Store the targets aggregated over the analyzed references of recipe
    recipe_id and llm's description of them."""
    with Session(engine) as session:
        recipe = session.get(StyleRecipeRow, recipe_id)
        if recipe is None:
            return
        name = recipe.name
        targets = aggregate(recipe.features.get("references", {}).values())
    description = describe(name, targets, llm, engine=engine)
    with Session(engine) as session:
        recipe = session.get(StyleRecipeRow, recipe_id)
        if recipe is None:
            return
        recipe.features = {**recipe.features, "targets": targets.model_dump()}
        recipe.description = description
        session.commit()


def update_recipe(
    session: Session, recipe_id: int, patch: StyleRecipePatch
) -> StyleRecipe | None:
    """Apply the editor's patch to recipe recipe_id and return it (None if
    it does not exist). Raises ValueError for an unknown metric or a blank
    name; nothing is stored then."""
    recipe = session.get(StyleRecipeRow, recipe_id)
    if recipe is None:
        return None
    if patch.name is not None and not patch.name.strip():
        raise ValueError("name must not be blank")
    if patch.targets is not None:
        check_targets(patch.targets)
        recipe.features = {**recipe.features, "targets": patch.targets.model_dump()}
    if patch.name is not None:
        recipe.name = patch.name.strip()
    if patch.description is not None:
        recipe.description = patch.description.strip()
    session.commit()
    session.refresh(recipe)
    return recipe.to_model()


def import_recipe(
    session: Session, data: StyleRecipeExport, now: datetime | None = None
) -> StyleRecipe:
    """Store an exported recipe as a new recipe without references: its
    name, description, reference count and targets. Raises ValueError for
    an unknown metric."""
    check_targets(data.targets)
    recipe = StyleRecipeRow(
        name=data.name,
        description=data.description.strip(),
        features={"targets": data.targets.model_dump()},
        reference_count=data.reference_count,
        created_at=now or datetime.now(UTC),
    )
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    return recipe.to_model()
