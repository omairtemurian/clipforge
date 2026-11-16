"""Usage meter endpoint (SPEC-v2 2.4): what the jobs used in a month."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Engine

from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError
from clipforge.usage import UsageSummary, month_summary, parse_month, utc_now

router = APIRouter()


@router.get("/usage")
def get_usage(
    engine: Annotated[Engine, Depends(get_engine)],
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> UsageSummary:
    """Return the totals per kind and per project of month ("YYYY-MM", default
    the current month, UTC), with the monthly caps. 422 if month is not valid."""
    try:
        day = utc_now().date() if month is None else parse_month(month)
    except ValueError as exc:
        raise ApiError(422, "validation_error", f"month {month!r} is invalid") from exc
    return month_summary(engine, day)
