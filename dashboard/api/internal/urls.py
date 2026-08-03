"""Routes for the Vue SPA. Mounted under /api/v2/."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import analytics, namespaces, requests, siglums, sync, tenants, users

router = DefaultRouter()
router.register(r'clusters', tenants.ClusterViewSet, basename='cluster')
router.register(r'tenants', tenants.TenantViewSet, basename='tenant')
router.register(r'namespaces', namespaces.NamespaceViewSet, basename='namespace')

urlpatterns = [
    path('', include(router.urls)),

    path('users/', users.UserListView.as_view(), name='api-users-list'),
    path('users/<str:email>/', users.UserDetailView.as_view(), name='api-users-detail'),
    path('siglums/', siglums.SiglumListView.as_view(), name='api-siglums-list'),
    path('requests/', requests.RequestTicketListView.as_view(), name='api-requests-list'),

    path('analytics/', analytics.GlobalAnalyticsView.as_view(), name='api-analytics'),
    path('sync/', sync.TriggerSyncView.as_view(), name='api-sync'),
    path('sync/status/', sync.SyncStatusView.as_view(), name='api-sync-status'),
]

# Unversioned aliases, mounted at the project root rather than under /api/v2/.
# Kept live because app.js still calls them; drop once the frontend pass moves
# it to the versioned paths above.
legacy_urlpatterns = [
    path('api/sync/', sync.LegacyTriggerSyncView.as_view(), name='api-sync-legacy'),
    path('api/sync/status/', sync.LegacySyncStatusView.as_view(), name='api-sync-status-legacy'),
]
