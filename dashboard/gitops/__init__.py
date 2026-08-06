"""GitOps repository -> database projection.

    fetcher     get the repository onto local disk
    walker      resolve paths to (cluster, tenant, namespace)
    parsers     turn each kind of YAML into records
    reconciler  delete what Git no longer has
    status      hold the sync lock and report progress

`run_sync` is the whole flow; the management command is a thin wrapper over it.
"""
import logging
import os

from django.db import transaction

from . import walker
from .layout import layout
from .parsers import (
    ParseContext, parse_chart, parse_namespace_values, parse_tenant_metadata,
    parse_templates,
)
from .reconciler import prune
from .state import SyncState

logger = logging.getLogger(__name__)

__all__ = ['run_sync', 'SyncState']


def _process_file(location, content, state):
    """Apply one file to the database inside its own transaction.

    Per file, not per sync. A transaction around the whole walk would hold
    SQLite's write lock for the entire run; WAL keeps readers unblocked but
    writers still serialise, and every authenticated request writes the session
    row, so one long transaction would stall every page load until the busy
    timeout. Per file the lock is held for milliseconds.

    It is also the granularity that matters: the damaging failure is a torn
    namespace -- user access rows deleted and then not recreated -- not a
    half-finished repository, which the next sync fixes anyway.
    """
    import yaml  # local: keeps module import cheap for callers that only need types

    with transaction.atomic():
        cluster, tenant, namespace = walker.ensure_records(location, state)
        ctx = ParseContext(cluster=cluster, tenant=tenant, namespace=namespace, state=state)

        # templates/ holds raw manifests, possibly several per file, and is never
        # a config document -- so it is handled before anything is parsed as one.
        if location.is_template:
            parse_templates(content, ctx)
            return

        payload = yaml.safe_load(content)
        if not payload:
            return

        names = layout()
        if location.filename == names.tenant_metadata_file:
            parse_tenant_metadata(payload, ctx)
        elif location.filename == names.chart_file:
            parse_chart(payload, ctx)
        else:
            parse_namespace_values(payload, ctx)


def run_sync(repo_path, report=None, log=None):
    """Walk `repo_path` and project it into the database.

    report: progress messages for the UI. log: human-readable command output.
    Returns (configured_namespace_count, PruneResult).
    """
    def _log(message):
        if log:
            log(message)

    if report:
        report("Parsing configuration files...")

    state = SyncState()

    for location in walker.iter_locations(repo_path):
        content = walker.read_text(location.full_path)
        if content is None:
            continue

        try:
            _process_file(location, content, state)
        except Exception as exc:
            # One malformed file must not cost us the other 796 namespaces. The
            # transaction above has already rolled back this file's writes, so
            # the database still holds its last good version of them.
            #
            # No exc_info: a malformed YAML file is an expected, handled
            # condition, and the exception text already names the file, line and
            # column. A traceback per bad file would bury the rest of the run.
            logger.warning("Failed to process %s: %s", location.full_path, exc)
            _log(f"Failed to process content of {location.full_path}: {exc}")

    result = prune(state)
    if result.total:
        _log(f"Pruned stale records: {result}")

    return len(state.configured_namespaces), result


def sync_repository(local_path, report=None, log=None):
    """Fetch the repository and sync it. Returns (count, PruneResult) or None
    if the path could not be found."""
    from .fetcher import repository  # local: avoids importing requests at app load

    with repository(local_path, log=log) as repo_path:
        if not os.path.exists(repo_path):
            _msg = f"Directory not found: {repo_path}"
            if log:
                log(f"{_msg}. Aborting sync.")
            return None, _msg

        count, result = run_sync(repo_path, report=report, log=log)
        return (count, result), None
