"""SystemSyncStatus transitions and the concurrency lock.

The lock itself lives on the model as a conditional UPDATE (see
SystemSyncStatus.try_acquire); this module wraps it in the acquire/release
lifecycle a sync run needs, so no caller has to remember to release.
"""
import logging
from contextlib import contextmanager

from dashboard.models import SystemSyncStatus, SyncAlreadyRunning

logger = logging.getLogger(__name__)


@contextmanager
def sync_lock(already_held=False, initial_message="Fetching repository..."):
    """Hold the sync lock for the duration of the block.

    Gates every caller, not just the HTTP one: the polling sidecar invokes the
    management command directly, so a guard living only in TriggerSyncView left
    a manual sync and an inbound pipeline free to write the same SQLite file at
    once.

    Yields a `report` callable for progress messages. On the way out the lock is
    always released -- only a clean exit advances last_sync_time, so a failed
    run cannot make the UI think fresh data arrived.

    already_held: the caller took the lock itself (TriggerSyncView does, so its
    409 is accurate before it spawns a worker thread). Without this the command
    would refuse its own caller.
    """
    if not already_held and not SystemSyncStatus.try_acquire(initial_message):
        raise SyncAlreadyRunning("A sync is already in progress; skipping this run.")

    outcome = {"completed": False, "message": "Sync failed"}

    def report(message):
        SystemSyncStatus.set_message(message)

    def finish(message, completed=False):
        outcome["message"] = message[:255]
        outcome["completed"] = completed

    report.finish = finish

    try:
        yield report
    except Exception as exc:
        outcome["message"] = f"Sync Error: {exc}"[:255]
        raise
    finally:
        SystemSyncStatus.release(outcome["message"], completed=outcome["completed"])
