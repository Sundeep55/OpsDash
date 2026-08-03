"""Sync control: status polling and manual trigger."""
import logging
import threading

from django.core.management import call_command
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import generics, serializers
from rest_framework.response import Response

from dashboard.models import SyncAlreadyRunning, SystemSyncStatus

logger = logging.getLogger(__name__)


def run_sync_task():
    try:
        # The view already claimed the lock; sync_gitops must not try to re-take it.
        call_command('sync_gitops', lock_held=True)
    except SyncAlreadyRunning:
        logger.info("Manual sync skipped: another sync already holds the lock.")
    except Exception:
        # sync_gitops releases the lock in its own finally block; this only needs
        # to make sure the failure is visible. It used to be a bare `pass`, so a
        # failing background sync left no trace anywhere.
        logger.exception("Background GitOps sync failed")


class SyncStatusView(generics.GenericAPIView):
    serializer_class = serializers.Serializer
    
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        status = SystemSyncStatus.get_state()
        return Response({
            "is_syncing": status.is_syncing,
            "last_message": status.last_message,
            "last_sync_time": status.last_sync_time.isoformat() if status.last_sync_time else None
        })


class TriggerSyncView(generics.GenericAPIView):
    serializer_class = serializers.Serializer
    
    @extend_schema(request=None, responses={202: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT})
    def post(self, request):
        # Claim the lock here rather than check-then-set, so two clicks landing on
        # two gunicorn workers cannot both spawn a sync thread. sync_gitops itself
        # re-acquires and would refuse the loser anyway, but taking it up front
        # keeps the 409 accurate instead of returning 202 for a sync that no-ops.
        if not SystemSyncStatus.try_acquire("Starting manual sync..."):
            return Response({"status": "already_running", "message": "A sync is already in progress."}, status=409)

        thread = threading.Thread(target=run_sync_task, daemon=True)
        thread.start()
        return Response({"status": "success", "message": "GitOps Sync started."}, status=202)
