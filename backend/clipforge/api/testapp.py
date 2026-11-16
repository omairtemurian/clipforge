"""The API in test mode, for the end-to-end tests (SPEC 9.6).

`uvicorn --factory clipforge.api.testapp:create_test_app` serves the API with
a worker whose jobs take the transcript of DIR/transcript.json instead of
whisper and answer every LLM prompt (curate, "Regenerate with AI") with
DIR/llm_response.json (see clipforge.testmode). It needs both
CLIPFORGE_TEST_MODE=1 and CLIPFORGE_FIXTURES_DIR=DIR and refuses to start
with only one of them, so a normal server never runs in test mode. The
creator watch does not poll and the posting worker does not publish (no
request leaves the machine). The stand-ins of api.testmode_routes (a
connected account, a creator's new upload) are under /api/testmode.
"""

import os
from collections.abc import Mapping
from pathlib import Path

from fastapi import FastAPI

from clipforge.api.app import API_PREFIX, create_app
from clipforge.api.testmode_routes import build_router
from clipforge.testmode import (
    ENV_VAR,
    RecordedLLM,
    offline_llm_transport,
    recorded_inputs,
)

FIXTURES_DIR_ENV_VAR = "CLIPFORGE_FIXTURES_DIR"


def create_test_app(environ: Mapping[str, str] = os.environ) -> FastAPI:
    """Return the app in test mode, configured from environ.

    Raises ValueError unless environ sets CLIPFORGE_TEST_MODE to "1" and
    CLIPFORGE_FIXTURES_DIR to a directory with transcript.json and
    llm_response.json.
    """
    fixtures = environ.get(FIXTURES_DIR_ENV_VAR)
    if environ.get(ENV_VAR) != "1" or not fixtures:
        raise ValueError(
            f"the test server needs {ENV_VAR}=1 and {FIXTURES_DIR_ENV_VAR}=DIR"
        )
    recorded = recorded_inputs(Path(fixtures), environ)
    if recorded is None:
        raise ValueError(f"{ENV_VAR}=1 did not turn test mode on")
    app = create_app(
        llm=RecordedLLM(recorded.llm_response),
        llm_transport=offline_llm_transport(),
        transcript=recorded.transcript,
        run_watch=False,
        run_posting=False,
    )
    app.include_router(build_router(Path(fixtures)), prefix=API_PREFIX)
    return app
