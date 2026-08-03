"""Routes for the "API as a Product" endpoints. Mounted under /api/v2/.

Paths here are a published contract. Renaming one breaks consumers silently,
so prefer adding a new path over changing an existing one.
"""
from django.urls import path

from . import devex, finops, network, platform, security, stack

urlpatterns = [
    path('platform/clusters/', platform.PlatformClusterApiView.as_view(), name='api-platform-clusters'),
    path('platform/gpu-allocations/', platform.PlatformGPUApiView.as_view(), name='api-platform-gpus'),

    path('finops/quotas/', finops.FinOpsQuotaApiView.as_view(), name='api-finops-quotas'),
    path('finops/unattributed-spend/', finops.FinOpsUnattributedApiView.as_view(), name='api-finops-unattributed'),

    path('devex/devspaces/', devex.DevExDevspaceApiView.as_view(), name='api-devex-devspaces'),
    path('devex/project-rosters/', devex.DevExRosterApiView.as_view(), name='api-devex-rosters'),

    path('security/route-exceptions/', security.SecurityRouteExceptionApiView.as_view(), name='api-security-route-exceptions'),
    path('security/robot-accounts/', security.SecurityRobotApiView.as_view(), name='api-security-robots'),
    path('security/namespace-posture/', security.SecurityPostureApiView.as_view(), name='api-security-posture'),

    path('stack/helm-deployments/', stack.StackHelmApiView.as_view(), name='api-stack-helm'),
    path('stack/upstream-mirrors/', stack.StackMirrorApiView.as_view(), name='api-stack-mirrors'),

    path('network/egress-routing/', network.NetworkEgressApiView.as_view(), name='api-network-egress'),
    path('network/service-mesh/', network.NetworkServiceMeshApiView.as_view(), name='api-network-servicemesh'),
]
