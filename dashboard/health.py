"""Health endpoints for the web container's kubelet probes.

Deliberately plain Django views rather than DRF: every API endpoint sits behind
IsAuthenticated, and a probe has no session, so routing these through DRF would
answer 403 and the container would never pass its checks.

The two answer different questions:

    /healthz  is this process alive?      -> restart the container if not
    /readyz   can it serve a request?     -> take it out of the Service if not

Liveness must not touch the database. If SQLite is briefly locked by a long
sync, a liveness probe that queried it would restart the very container holding
the connection, which turns a slow moment into a crash loop.
"""
import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
@never_cache
def liveness(request):
    """The process is running and can route a request. No dependencies."""
    return JsonResponse({'status': 'alive'})


@require_GET
@never_cache
def readiness(request):
    """The database is reachable and the schema is present.

    Deliberately does not check whether any data has synced yet. An empty
    database is a valid state -- it is what a fresh deployment looks like
    before its first sync, and the UI handles it by offering to run one.
    Gating readiness on row counts would keep a working container out of the
    Service until the sidecar happened to finish.
    """
    checks = {}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        checks['database'] = 'ok'
    except Exception as exc:
        logger.warning("Readiness: database unreachable: %s", exc)
        checks['database'] = f'unavailable ({type(exc).__name__})'
        healthy = False

    if healthy:
        # A table that only exists once migrations have run. Catches the window
        # where the volume is mounted but the schema was never applied.
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM dashboard_systemsyncstatus LIMIT 1')
                cursor.fetchone()
            checks['schema'] = 'ok'
        except Exception as exc:
            logger.warning("Readiness: schema not applied: %s", exc)
            checks['schema'] = f'missing ({type(exc).__name__})'
            healthy = False

    return JsonResponse(
        {'status': 'ready' if healthy else 'not-ready', 'checks': checks},
        status=200 if healthy else 503,
    )
