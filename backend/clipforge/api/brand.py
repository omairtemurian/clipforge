"""Brand template endpoints (SPEC 7): list, create, get, change and delete
templates, with the logo (and the optional intro and outro) as uploads.

Create and change take multipart forms. A template's files are kept in
{data_dir}/brand/<id>/ (clipforge.brand_files); logo_path, intro_path and
outro_path hold their paths, and GET /brand-templates/{id}/logo returns the
logo for the page's live preview. GET /brand-fonts lists the fonts a template
can name.
"""

from pathlib import Path
from typing import Annotated, TypeGuard

from fastapi import APIRouter, Depends, Form, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import brand_files
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.brand_style import DEFAULT_COLOR, DEFAULT_FONT
from clipforge.db import BrandTemplateRow
from clipforge.fonts import EMOJI_FONT, available_fonts
from clipforge.models import BrandTemplate, HexColor, LogoPosition, UnitInterval

router = APIRouter()


@router.get("/brand-fonts")
def list_brand_fonts() -> list[str]:
    """Return the names a template's font can be (bundled and uploaded fonts),
    without the emoji font."""
    return sorted(name for name in available_fonts() if not name.startswith(EMOJI_FONT))


@router.get("/brand-templates")
def list_brand_templates(
    engine: Annotated[Engine, Depends(get_engine)],
) -> list[BrandTemplate]:
    """Return every brand template, oldest first."""
    with Session(engine) as session:
        rows = session.exec(select(BrandTemplateRow).order_by(col(BrandTemplateRow.id)))
        return [row.to_model() for row in rows]


@router.post("/brand-templates", status_code=201)
def create_brand_template(
    engine: Annotated[Engine, Depends(get_engine)],
    name: Annotated[str, Form()],
    logo: UploadFile,
    logo_position: Annotated[LogoPosition, Form()] = "br",
    logo_opacity: Annotated[UnitInterval, Form()] = 0.8,
    font: Annotated[str, Form()] = DEFAULT_FONT,
    primary_color: Annotated[HexColor, Form()] = DEFAULT_COLOR,
    intro: UploadFile | None = None,
    outro: UploadFile | None = None,
) -> BrandTemplate:
    """Create a template; the logo is a PNG, JPEG or WebP, intro and outro
    are optional videos. 422 for an invalid field or file."""
    row = BrandTemplateRow(
        name=_name(name),
        logo_path="",
        logo_position=logo_position,
        logo_opacity=logo_opacity,
        font=_font(font),
        primary_color=primary_color,
    )
    with brand_files.staging_dir() as staging, Session(engine) as session:
        staged = _stage(staging, logo, intro, outro)
        if "logo" not in staged:
            raise ApiError(422, "validation_error", "logo: a file is required")
        session.add(row)
        session.flush()
        assert row.id is not None
        _set_paths(row, staged)
        session.commit()
        brand_files.publish(row.id, list(staged.values()))
        return row.to_model()


@router.get("/brand-templates/{template_id}")
def get_brand_template(
    template_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> BrandTemplate:
    """Return one brand template."""
    with Session(engine) as session:
        return _row(session, template_id).to_model()


@router.put("/brand-templates/{template_id}")
def change_brand_template(
    template_id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    name: Annotated[str | None, Form()] = None,
    logo_position: Annotated[LogoPosition | None, Form()] = None,
    logo_opacity: Annotated[UnitInterval | None, Form()] = None,
    font: Annotated[str | None, Form()] = None,
    primary_color: Annotated[HexColor | None, Form()] = None,
    remove_intro: Annotated[bool, Form()] = False,
    remove_outro: Annotated[bool, Form()] = False,
    logo: UploadFile | None = None,
    intro: UploadFile | None = None,
    outro: UploadFile | None = None,
) -> BrandTemplate:
    """Change a template: a field or file that is absent keeps its value;
    remove_intro / remove_outro drop that video (unless a new one is sent)."""
    with brand_files.staging_dir() as staging, Session(engine) as session:
        row = _row(session, template_id)
        if name is not None:
            row.name = _name(name)
        if font is not None:
            row.font = _font(font)
        if logo_position is not None:
            row.logo_position = logo_position
        if logo_opacity is not None:
            row.logo_opacity = logo_opacity
        if primary_color is not None:
            row.primary_color = primary_color
        staged = _stage(staging, logo, intro, outro)
        _set_paths(row, staged)
        dropped = [
            kind
            for kind, drop, file in (
                ("intro", remove_intro, intro),
                ("outro", remove_outro, outro),
            )
            if drop and not _sent(file)
        ]
        for kind in dropped:
            setattr(row, f"{kind}_path", None)
        session.add(row)
        session.commit()
        for kind in dropped:
            brand_files.remove_video(template_id, kind)
        brand_files.publish(template_id, list(staged.values()))
        return row.to_model()


@router.delete("/brand-templates/{template_id}", status_code=204)
def delete_brand_template(
    template_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Delete a template and its files."""
    with Session(engine) as session:
        session.delete(_row(session, template_id))
        session.commit()
    brand_files.remove_files(template_id)
    return Response(status_code=204)


@router.get("/brand-templates/{template_id}/logo")
def get_brand_logo(
    template_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> FileResponse:
    """Return the logo image of a template."""
    with Session(engine) as session:
        path = Path(_row(session, template_id).logo_path)
    if not path.is_file():
        raise not_found("logo of brand template", template_id)
    return FileResponse(path)


def _row(session: Session, template_id: int) -> BrandTemplateRow:
    """Return template template_id's row; raises the 404 ApiError if missing."""
    row = session.get(BrandTemplateRow, template_id)
    if row is None:
        raise not_found("brand template", template_id)
    return row


def _name(name: str) -> str:
    """Return name without surrounding blanks; raises the 422 ApiError if empty."""
    if not name.strip():
        raise ApiError(422, "validation_error", "name: must not be empty")
    return name.strip()


def _font(font: str) -> str:
    """Return font if it is a bundled or uploaded font; raises the 422 ApiError
    if not."""
    known = available_fonts()
    if font not in known:
        names = ", ".join(sorted(known))
        raise ApiError(422, "validation_error", f"font: {font!r} is not one of {names}")
    return font


def _stage(
    staging: Path,
    logo: UploadFile | None,
    intro: UploadFile | None,
    outro: UploadFile | None,
) -> dict[str, Path]:
    """Stage the uploads that were sent, validated, by kind. A file input
    left empty (no name, no bytes), as browsers send it, counts as not sent."""
    staged: dict[str, Path] = {}
    if _sent(logo):
        staged["logo"] = brand_files.stage_logo(staging, logo)
    for kind, file in (("intro", intro), ("outro", outro)):
        if _sent(file):
            staged[kind] = brand_files.stage_video(staging, file, kind)
    return staged


def _sent(file: UploadFile | None) -> TypeGuard[UploadFile]:
    """Tell whether file is an upload that the client filled in."""
    return file is not None and bool(file.filename or file.size)


def _set_paths(row: BrandTemplateRow, staged: dict[str, Path]) -> None:
    """Point the row's file paths at where publish will put the staged files."""
    assert row.id is not None
    for kind, path in staged.items():
        setattr(row, f"{kind}_path", str(brand_files.final_path(row.id, path)))
