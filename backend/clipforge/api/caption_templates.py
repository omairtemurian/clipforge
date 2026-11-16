"""Caption template endpoints (SPEC 7): the templates with preview images,
and live previews of a template with a caption style (SPEC-v2 3.4)."""

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from clipforge.api.errors import ApiError
from clipforge.caption_previews import ensure_preview, styled_preview
from clipforge.captions_templates import (
    CaptionTemplate,
    load_templates,
    style_problems,
)
from clipforge.models import CaptionStyle

router = APIRouter()


class CaptionTemplateInfo(BaseModel):
    """A caption template and where its preview image is."""

    name: str
    template: CaptionTemplate
    preview_url: str


@router.get("/caption-templates")
def list_caption_templates() -> list[CaptionTemplateInfo]:
    """Return every caption template, in name order."""
    return [
        CaptionTemplateInfo(
            name=name,
            template=template,
            preview_url=f"/api/caption-templates/{name}/preview.png",
        )
        for name, template in load_templates().items()
    ]


@router.get("/caption-templates/{name}/preview.png")
def get_caption_template_preview(name: str) -> FileResponse:
    """Return the preview PNG of a template (drawn now if not cached yet)."""
    return FileResponse(ensure_preview(name, known(name)), media_type="image/png")


@router.post(
    "/caption-templates/{name}/preview",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def post_caption_template_preview(name: str, style: CaptionStyle) -> Response:
    """Return a PNG of the template's sample caption with style applied: the
    live preview of a caption style being edited (not cached)."""
    template = known(name)
    problems = style_problems(style)
    if problems:
        raise ApiError(422, "validation_error", "; ".join(problems))
    return Response(styled_preview(template, style), media_type="image/png")


def known(name: str) -> CaptionTemplate:
    """Return the template called name; ApiError 404 if there is none."""
    templates = load_templates()
    if name not in templates:
        raise ApiError(404, "not_found", f"caption template {name!r} not found")
    return templates[name]
