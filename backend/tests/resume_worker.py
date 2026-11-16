"""A worker process that test_job_resume kills in the middle of a job.

Usage: python resume_worker.py HANG_AT REACHED TRANSCRIPT

Claims the next queued job of the database in the configured data directory
(DATA_DIR) and runs it with the fake LLM and the transcript TRANSCRIPT. The
real steps run, except the step HANG_AT: when the job reaches it, the file
REACHED is written and the step waits until the process is killed.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clipforge import process  # noqa: E402
from clipforge.db import init_db  # noqa: E402
from clipforge.jobs import run_next  # noqa: E402
from clipforge.pipeline.step import Step, StepSettings  # noqa: E402
from fakes import FakeLLMClient  # noqa: E402


def main(hang_at: str, reached: Path, transcript: Path) -> None:
    """Run the next job with the step hang_at replaced by a wait that never
    ends; reached is written when the wait starts."""
    real_load_step = process.load_step

    def hang(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
        reached.write_text(hang_at, encoding="utf-8")
        while True:
            time.sleep(1)

    def load_step(name: str) -> Step:
        return hang if name == hang_at else real_load_step(name)

    process.load_step = load_step
    run_next(init_db(), llm=FakeLLMClient(), transcript=transcript)


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
