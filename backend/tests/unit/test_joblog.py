"""Tests of the job log file."""

import logging
from pathlib import Path

from clipforge.joblog import job_log


def test_job_log_writes_info_records_whatever_the_package_level(
    tmp_path: Path,
) -> None:
    package = logging.getLogger("clipforge")
    before = package.level
    package.setLevel(logging.WARNING)
    path = tmp_path / "work" / "7" / "job.log"
    try:
        with job_log(path):
            logging.getLogger("clipforge.process").info("step ingest")
            logging.getLogger("other.library").info("not ours")
        logging.getLogger("clipforge.process").warning("after the block")
        assert package.level == logging.WARNING
    finally:
        package.setLevel(before)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert lines[0].endswith("INFO clipforge.process: step ingest")
