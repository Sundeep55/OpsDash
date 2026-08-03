"""Flat serializers for the "API as a Product" endpoints.

These are a published contract with the teams that scrape them, so treat field
names and shapes as stable. Every one is intentionally flat -- one row per
record with its identifiers denormalised onto it -- so a consumer can load a
response straight into a table without walking nested objects.
"""
from rest_framework import serializers

from dashboard.models import RouteException

class PlatformClusterMetricsSerializer(serializers.Serializer):
    cluster_name = serializers.CharField()
    total_tenants = serializers.IntegerField()
    total_namespaces = serializers.IntegerField()
    total_cpu_requests = serializers.FloatField()
    total_cpu_limits = serializers.FloatField()
    total_mem_requests_gb = serializers.FloatField()
    total_mem_limits_gb = serializers.FloatField()
    total_gpus_allocated = serializers.IntegerField()

class GPUAllocationFlatSerializer(serializers.Serializer):
    cluster = serializers.CharField()
    namespace = serializers.CharField()
    tenant = serializers.CharField()
    allocation_type = serializers.CharField()
    gpu_count = serializers.IntegerField()
    limit_min = serializers.CharField(allow_null=True)
    limit_max = serializers.CharField(allow_null=True)
    limit_default = serializers.CharField(allow_null=True)
    limit_default_request = serializers.CharField(allow_null=True)

class FinOpsQuotaFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    tenant = serializers.CharField()
    cost_center = serializers.CharField()
    siglum = serializers.CharField()
    cpu_requests = serializers.FloatField()
    cpu_limits = serializers.FloatField()
    mem_requests_gb = serializers.FloatField()
    mem_limits_gb = serializers.FloatField()
    storage_requests_gb = serializers.FloatField()

class FinOpsUnattributedSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    tenant = serializers.CharField()
    cluster = serializers.CharField()
    cpu_requests = serializers.FloatField()
    mem_requests_gb = serializers.FloatField()
    reason = serializers.CharField()

class DevSpaceFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    devspace_user = serializers.EmailField()
    cluster = serializers.CharField()
    cpu_requests = serializers.FloatField()
    mem_requests_gb = serializers.FloatField()

class ProjectRosterSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    owners = serializers.ListField(child=serializers.EmailField())
    users = serializers.ListField(child=serializers.EmailField())

class RouteExceptionFlatSerializer(serializers.ModelSerializer):
    namespace = serializers.CharField(source='namespace.name', read_only=True)
    tenant = serializers.CharField(source='namespace.tenant.name', read_only=True)
    cluster = serializers.CharField(source='namespace.cluster.name', read_only=True)
    
    class Meta:
        model = RouteException
        fields = ['namespace', 'tenant', 'cluster', 'is_active', 'request_id', 'granted_at']

class SecurityPostureFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    cluster = serializers.CharField()
    tenant = serializers.CharField()
    harbor_enabled = serializers.BooleanField()
    vulnerability_scanning = serializers.BooleanField()
    auto_sbom_generation = serializers.BooleanField()
    cve_allowlist_count = serializers.IntegerField()
    s3_connection_enabled = serializers.BooleanField()


class RobotAccountFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    account_name = serializers.CharField()
    is_default = serializers.BooleanField()
    permissions_count = serializers.IntegerField()

class HelmDeploymentFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    cluster = serializers.CharField()
    chart_name = serializers.CharField()
    version = serializers.CharField()

class RegistryMirrorFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    cluster = serializers.CharField()
    mirror_name = serializers.CharField()
    endpoint_url = serializers.URLField()
    image = serializers.CharField()

class EgressRoutingFlatSerializer(serializers.Serializer):
    namespace = serializers.CharField()
    cluster = serializers.CharField()
    egress_router = serializers.CharField()
    egress_ips = serializers.ListField(child=serializers.CharField())

class ServiceMeshFlatSerializer(serializers.Serializer):
    control_plane_namespace = serializers.CharField()
    cluster = serializers.CharField()
    domain = serializers.CharField()
    dataplane_namespaces = serializers.ListField(child=serializers.CharField())
