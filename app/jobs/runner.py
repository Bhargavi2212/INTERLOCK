"""In-process background jobs (one Cloud Run instance; --no-cpu-throttling).

Job state lives in the store after every step. A failed job records the
exception class name only (messages can carry request details).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from app.store.base import get_store

log = logging.getLogger("interlock.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
INLINE = False  # tests run jobs synchronously


def submit(job_id: str, fn: Callable[[], dict | None]) -> None:
    def run():
        store = get_store()
        store.update_job(job_id, {"state": "running"})
        try:
            result = fn() or {}
            store.update_job(job_id, {"state": "done", "result": result})
        except Exception as e:  # recorded by class name only
            log.warning("job %s failed: %s", job_id, type(e).__name__)
            store.update_job(job_id, {"state": "failed", "error": type(e).__name__})

    if INLINE:
        run()
    else:
        _pool.submit(run)


def fail_unfinished_on_startup() -> int:
    """Jobs left queued/running by a restart are marked failed; the page offers 'run again'."""
    store = get_store()
    jobs = store.unfinished_jobs()
    for j in jobs:
        store.update_job(j["job_id"], {"state": "failed", "error": "server restarted"})
    return len(jobs)
