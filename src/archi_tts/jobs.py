"""Single-worker job queue: engines run one synthesis at a time."""

from __future__ import annotations

import queue
import sys
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .pipeline import RenderResult


@dataclass
class Job:
    id: str
    name: str
    status: str = "queued"          # queued | running | done | error
    done: int = 0
    total: int = 0
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    result: RenderResult | None = None
    error: str | None = None
    event: threading.Event = field(default_factory=threading.Event, repr=False)

    def as_dict(self) -> dict:
        d = {"job_id": self.id, "name": self.name, "status": self.status}
        if self.total:
            d["progress"] = f"{self.done}/{self.total} câu ({round(100 * self.done / self.total)}%)"
        if self.status == "running" and self.started and self.done:
            rate = (time.time() - self.started) / self.done
            d["eta_s"] = round(rate * (self.total - self.done))
        if self.result:
            d["result"] = self.result.as_dict()
        if self.error:
            d["error"] = self.error
        return d


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self._q: queue.Queue[tuple[Job, Callable]] = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="tts-worker").start()

    def submit(self, name: str, fn: Callable[[Callable[[int, int], None]], RenderResult]) -> Job:
        job = Job(id=uuid.uuid4().hex[:8], name=name)
        self.jobs[job.id] = job
        self._q.put((job, fn))
        return job

    def _worker(self) -> None:
        while True:
            job, fn = self._q.get()
            job.status, job.started = "running", time.time()

            def progress(done: int, total: int, job=job) -> None:
                job.done, job.total = done, total

            try:
                job.result = fn(progress)
                job.status = "done"
            except Exception as e:  # report, keep the worker alive
                job.status, job.error = "error", f"{type(e).__name__}: {e}"
                traceback.print_exc(file=sys.stderr)
            finally:
                job.finished = time.time()
                job.event.set()

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)
