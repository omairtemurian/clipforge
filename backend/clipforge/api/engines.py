"""Capability endpoint (SPEC-v2 2.3): which optional engines are installed."""

from fastapi import APIRouter

from clipforge.engines import EngineStatus, engine_statuses

router = APIRouter()


@router.get("/engines")
def get_engines(refresh: bool = False) -> list[EngineStatus]:
    """Return every optional engine with its capability flag (`installed`).

    The checks are cached; `refresh=true` runs them again (after the user
    installed an engine).
    """
    return engine_statuses(refresh=refresh)
