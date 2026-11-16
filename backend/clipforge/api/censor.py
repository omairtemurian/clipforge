"""Custom censor list endpoints (SPEC-v2 3.4, pipeline/censor):

    GET /censor-words               -> CensorWords
    PUT /censor-words  CensorWords  -> CensorWords

The custom list adds to the default list of the captions' language; it takes
effect at a clip's next render or preview. Per-word censoring is a clip's
caption_style (word_marks[].censor, censor), saved with PATCH /clips/{id}.
"""

from fastapi import APIRouter

from clipforge.api.errors import ApiError
from clipforge.models import CensorWords
from clipforge.pipeline import censor
from clipforge.pipeline.step import StepError

router = APIRouter()


@router.get("/censor-words")
def get_censor_words() -> CensorWords:
    """Return the custom censor list (empty if none was saved); 409 if its
    file is not valid."""
    try:
        return censor.load_custom()
    except StepError as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.put("/censor-words")
def put_censor_words(body: CensorWords) -> CensorWords:
    """Save body as the custom censor list and return it."""
    censor.save_custom(body)
    return body
