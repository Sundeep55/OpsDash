"""Routes for the Vue SPA. Mounted under /api/v2/."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import (analytics, capsules, namespaces, pipeline, requests, siglums,
               sync, tenants, users)

router = DefaultRouter()
router.register(r'clusters', tenants.ClusterViewSet, basename='cluster')
router.register(r'tenants', tenants.TenantViewSet, basename='tenant')
router.register(r'namespaces', namespaces.NamespaceViewSet, basename='namespace')

urlpatterns = [
    path('', include(router.urls)),

    path('capsules/', capsules.CapsuleListApiView.as_view(), name='api-capsules'),
    path('capsules/<str:name>/', capsules.CapsuleDetailApiView.as_view(), name='api-capsule-detail'),
    path('users/', users.UserListView.as_view(), name='api-users-list'),
    path('users/<str:email>/', users.UserDetailView.as_view(), name='api-users-detail'),
    path('siglums/', siglums.SiglumListView.as_view(), name='api-siglums-list'),
    path('requests/', requests.RequestTicketListView.as_view(), name='api-requests-list'),

    path('analytics/', analytics.GlobalAnalyticsView.as_view(), name='api-analytics'),
    path('sync/', sync.TriggerSyncView.as_view(), name='api-sync'),
    path('sync/status/', sync.SyncStatusView.as_view(), name='api-sync-status'),

    # Onboarding pipeline. The only write path in the dashboard, and it writes
    # to GitLab rather than to anything here.
    path('pipeline/config/', pipeline.PipelineConfigView.as_view(), name='api-pipeline-config'),
    path('pipeline/schema/', pipeline.PipelineSchemaView.as_view(), name='api-pipeline-schema'),
    path('pipeline/index/', pipeline.PipelineIndexView.as_view(), name='api-pipeline-index'),
    path('pipeline/trigger/', pipeline.PipelineTriggerView.as_view(), name='api-pipeline-trigger'),
]
