"""Serializers, split by consumer.

    core.py   the internal API behind the Vue SPA
    flat.py   the "API as a Product" endpoints other teams scrape

Re-exported here so `from dashboard.serializers import X` keeps working
regardless of which module X lives in.
"""
from .core import (
    ClusterSerializer,
    NamespaceDetailSerializer,
    NamespaceListSerializer,
    NamespaceSerializer,
    TenantDetailSerializer,
    TenantSerializer,
    UserListSerializer,
)
from .flat import (
    DevSpaceFlatSerializer,
    EgressRoutingFlatSerializer,
    FinOpsQuotaFlatSerializer,
    FinOpsUnattributedSerializer,
    GPUAllocationFlatSerializer,
    HelmDeploymentFlatSerializer,
    PlatformClusterMetricsSerializer,
    ProjectRosterSerializer,
    RegistryMirrorFlatSerializer,
    RobotAccountFlatSerializer,
    RouteExceptionFlatSerializer,
    SecurityPostureFlatSerializer,
    ServiceMeshFlatSerializer,
)

__all__ = [
    "ClusterSerializer",
    "DevSpaceFlatSerializer",
    "EgressRoutingFlatSerializer",
    "FinOpsQuotaFlatSerializer",
    "FinOpsUnattributedSerializer",
    "GPUAllocationFlatSerializer",
    "HelmDeploymentFlatSerializer",
    "NamespaceDetailSerializer",
    "NamespaceListSerializer",
    "NamespaceSerializer",
    "PlatformClusterMetricsSerializer",
    "ProjectRosterSerializer",
    "RegistryMirrorFlatSerializer",
    "RobotAccountFlatSerializer",
    "RouteExceptionFlatSerializer",
    "SecurityPostureFlatSerializer",
    "ServiceMeshFlatSerializer",
    "TenantDetailSerializer",
    "TenantSerializer",
    "UserListSerializer",
]
