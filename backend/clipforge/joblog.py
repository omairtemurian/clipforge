"""The log file of a job: the clipforge log records of a run, in its log_path."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


@contextmanager
def job_log(path: Path) -> Iterator[None]:
    """Also write the clipforge log records to path while the block runs.

    Records of INFO and above are written, even if the logging configuration
    lets only warnings through (as in the API server); the level of the
    package logger is put back afterwards.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.setLevel(logging.INFO)
    package_logger = logging.getLogger("clipforge")
    level = package_logger.level
    package_logger.addHandler(handler)
    if not 0 < package_logger.getEffectiveLevel() <= logging.INFO:
        package_logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        package_logger.setLevel(level)
        package_logger.removeHandler(handler)
        handler.close()
