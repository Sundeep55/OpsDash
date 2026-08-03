from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from dashboard import api_views

router = DefaultRouter()
router.register(r'clusters', api_views.ClusterViewSet, basename='cluster')
router.register(r'tenants', api_views.TenantViewSet, basename='tenant')
router.register(r'namespaces', api_views.NamespaceViewSet, basename='namespace')

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- AUTHENTICATION URLS ---
    path('accounts/', include('django.contrib.auth.urls')),
    
    path('', include('dashboard.urls')),
    
    # --- V2 DATA ENDPOINTS ---
    path('api/v2/', include(router.urls)),
    path('api/v2/users/', api_views.UserListView.as_view(), name='api-users-list'),
    path('api/v2/users/<str:email>/', api_views.UserDetailView.as_view(), name='api-users-detail'),
    path('api/v2/siglums/', api_views.SiglumListView.as_view(), name='api-siglums-list'),
    path('api/v2/requests/', api_views.RequestTicketListView.as_view(), name='api-requests-list'),
    
    # --- NEW "API AS A PRODUCT" ENDPOINTS ---
    path('api/v2/platform/clusters/', api_views.PlatformClusterApiView.as_view(), name='api-platform-clusters'),
    path('api/v2/platform/gpu-allocations/', api_views.PlatformGPUApiView.as_view(), name='api-platform-gpus'),
    
    path('api/v2/finops/quotas/', api_views.FinOpsQuotaApiView.as_view(), name='api-finops-quotas'),
    path('api/v2/finops/unattributed-spend/', api_views.FinOpsUnattributedApiView.as_view(), name='api-finops-unattributed'),
    
    path('api/v2/devex/devspaces/', api_views.DevExDevspaceApiView.as_view(), name='api-devex-devspaces'),
    path('api/v2/devex/project-rosters/', api_views.DevExRosterApiView.as_view(), name='api-devex-rosters'),
    
    # NEW: Updated URL and API View Name
    path('api/v2/security/route-exceptions/', api_views.SecurityRouteExceptionApiView.as_view(), name='api-security-route-exceptions'),
    path('api/v2/security/robot-accounts/', api_views.SecurityRobotApiView.as_view(), name='api-security-robots'),
    path('api/v2/security/namespace-posture/', api_views.SecurityPostureApiView.as_view(), name='api-security-posture'),
    
    path('api/v2/stack/helm-deployments/', api_views.StackHelmApiView.as_view(), name='api-stack-helm'),
    path('api/v2/stack/upstream-mirrors/', api_views.StackMirrorApiView.as_view(), name='api-stack-mirrors'),
    
    path('api/v2/network/egress-routing/', api_views.NetworkEgressApiView.as_view(), name='api-network-egress'),
    path('api/v2/network/service-mesh/', api_views.NetworkServiceMeshApiView.as_view(), name='api-network-servicemesh'),

    # --- UI SYNC & ANALYTICS ENDPOINTS ---
    path('api/v2/sync/', api_views.TriggerSyncView.as_view(), name='api-sync'),
    path('api/v2/sync/status/', api_views.SyncStatusView.as_view(), name='api-sync-status'),
    path('api/v2/analytics/', api_views.GlobalAnalyticsView.as_view(), name='api-analytics'),

    # Unversioned aliases, kept live because app.js still calls them and the
    # frontend is a later pass. Drop once it targets the v2 paths above.
    path('api/sync/', api_views.LegacyTriggerSyncView.as_view(), name='api-sync-legacy'),
    path('api/sync/status/', api_views.LegacySyncStatusView.as_view(), name='api-sync-status-legacy'),
    
    # --- SWAGGER API DOCS ---
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]