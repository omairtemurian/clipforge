"""A background poller: the clock, interval and thread of the watches that
look for new sources (the inbox folder watch, Auto Import)."""

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

logger = logging.getLogger(__name__)


class Poller(ABC):
    """Calls poll() every interval seconds of clock().

    tick() polls when the interval has passed since the last poll (the first
    tick polls at once); start() runs tick() in a daemon thread until stop().
    poll() returns the ids of the projects it queued.
    """

    thread_name = "clipforge-poller"

    def __init__(
        self, *, interval: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.interval = interval
        self.clock = clock
        self._due = clock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @abstractmethod
    def poll(self) -> list[int]:
        """Look for new sources once; return the ids of the queued projects."""

    def tick(self) -> list[int]:
        """Poll if the interval has passed since the last poll, else do
        nothing; return the ids of the queued projects."""
        now = self.clock()
        if now < self._due:
            return []
        self._due = now + self.interval
        return self.poll()

    def start(self) -> None:
        """Poll in a daemon thread until stop(); RuntimeError if running."""
        if self._thread is not None:
            raise RuntimeError(f"{self.thread_name} is already started")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=self.thread_name, daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop the thread and wait up to timeout seconds for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("%s: polling failed", self.thread_name)
            self._stop.wait(min(self.interval, 1.0))
