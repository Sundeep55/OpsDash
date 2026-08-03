from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes
from datetime import date
from django.db.models import Prefetch
from .models import (
    Cluster, Tenant, EgressRouter, Namespace,
    ResourceQuota, LimitRange, GPUAllocation,
    ServiceMeshControlPlane, NetworkPolicy, RouteException, HarborConfig,
    Operator, HelmDeployment, RegistryMirror, CustomResource,
    RobotAccount, NetworkConnection, UserAccess
)

class ClusterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cluster
        fields = '__all__'

class TenantSerializer(serializers.ModelSerializer):
    active_ns_count = serializers.IntegerField(read_only=True, default=0)
    class Meta:
        model = Tenant
        fields = '__all__'

class TenantDetailSerializer(TenantSerializer):
    active_namespaces = serializers.SerializerMethodField()
    decommissioned_namespaces = serializers.SerializerMethodField()
    has_cso = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        fields = '__all__'

    # The tenant detail panel renders namespaces as a table, so it takes the list
    # payload. It previously used the full serializer while select_related'ing
    # only four of the nine relations that serializer touches, so every tenant
    # detail load fired a burst of per-namespace queries and shipped the raw YAML
    # of every custom resource.
    @extend_schema_field(OpenApiTypes.ANY)
    def get_active_namespaces(self, obj):
        qs = NamespaceListSerializer.optimize(obj.namespaces.filter(is_decommissioned=False))
        return NamespaceListSerializer(qs, many=True).data

    @extend_schema_field(OpenApiTypes.ANY)
    def get_decommissioned_namespaces(self, obj):
        qs = NamespaceListSerializer.optimize(obj.namespaces.filter(is_decommissioned=True))
        return NamespaceListSerializer(qs, many=True).data
        
    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_cso(self, obj):
        return obj.namespaces.filter(egress_router__isnull=False).exists()

class UserListSerializer(serializers.Serializer):
    email = serializers.CharField()
    access_count = serializers.IntegerField()

# =====================================================================
# "API AS A PRODUCT" - SPECIALIZED FLAT SERIALIZERS
# =====================================================================

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
    gpu_tier = serializers.CharField()
    allocation_type = serializers.CharField()
    gpu_count = serializers.IntegerField()

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

# =====================================================================
# NAMESPACE SERIALIZERS (UI-DRIVEN)
#
# Split list vs detail, mirroring the Tenant pattern. One serializer used to
# serve both, so every row of a 50- (or 500-) row table carried the raw YAML of
# every custom resource plus nine relations the table never renders.
# =====================================================================

class _NamespaceFieldsMixin:
    """Method fields whose output is identical in the list and detail payloads."""

    @extend_schema_field(OpenApiTypes.STR)
    def get_siglum(self, obj):
        return obj.effective_siglum

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_routeException(self, obj):
        re_obj = getattr(obj, 'route_exception', None)
        if not re_obj or not re_obj.is_active:
            return {"enabled": False, "status": "inactive"}

        status = "active"
        days_active = 0
        if re_obj.granted_at:
            days_active = (date.today() - re_obj.granted_at).days
            if days_active > 90:
                status = "expired"

        return {
            "enabled": True,
            "status": status,
            "requestId": re_obj.request_id,
            "grantedAt": re_obj.granted_at,
            "daysActive": days_active
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_operators(self, obj):
        return {op.name: {"enabled": op.is_enabled} for op in obj.operators.all()}

    @extend_schema_field(OpenApiTypes.ANY)
    def get_registry_mirrors(self, obj):
        return [{"name": m.name, "image": m.image, "tag": m.tag, "endpoint_url": m.endpoint_url} for m in obj.registry_mirrors.all()]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_harbor(self, obj):
        h = getattr(obj, 'harbor_config', None)
        return {
            "enable": h.is_enabled if h else False,
            "storageQuota": h.storage_quota_gb if h else 0,
            "cveAllowlist": h.cve_allowlist if h and h.cve_allowlist else []
        }


class NamespaceListSerializer(_NamespaceFieldsMixin, serializers.ModelSerializer):
    """Trimmed payload for every table/list view of namespaces.

    Field set is exactly what the consuming templates read, established by
    grepping them rather than guessing:

        namespaces/list.html   the namespaces table
        dashboard_tab.html     the KPI drill-down (fetches page_size=500)
        tenants/detail.html    the tenant's namespace panel
        siglums_tab.html       the siglum match list

    Two fields are deliberately narrower than their detail counterparts, because
    no list consumer reads past them:

        network_flows  omits 'connections' (only namespaces/detail.html renders
                       it), which drops the network_connections query entirely
        templates      omits 'content', the raw YAML of every custom resource --
                       every consumer here only reads templates.length

    Not built by subclassing the detail serializer: the cost is in the method
    fields, so inheriting would compute them and then throw them away.
    """
    cluster = serializers.CharField(source='cluster.name', read_only=True)
    tenant = serializers.CharField(source='tenant.name', read_only=True)

    network_flows = serializers.SerializerMethodField()
    routeException = serializers.SerializerMethodField()
    operators = serializers.SerializerMethodField()
    registry_mirrors = serializers.SerializerMethodField()
    templates = serializers.SerializerMethodField()
    harbor = serializers.SerializerMethodField()

    class Meta:
        model = Namespace
        fields = [
            'name', 'tenant', 'cluster', 'lifecycle', 'is_devspace', 'is_cso',
            'is_decommissioned', 'network_flows', 'routeException', 'operators',
            'registry_mirrors', 'templates', 'harbor',
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_network_flows(self, obj):
        np = getattr(obj, 'network_policy', None)
        return {
            "enabled": np.flows_enabled if np else False,
            "dns": np.dns_resolution_enabled if np else False,
            "proxy": np.proxy_enabled if np else False,
        }

    @extend_schema_field(OpenApiTypes.ANY)
    def get_templates(self, obj):
        return [{"kind": c.kind, "name": c.name} for c in obj.custom_resources.all()]

    @staticmethod
    def optimize(queryset):
        """Attach exactly the relations this serializer reads -- and no others.

        Kept beside the field definitions so the two cannot drift: the previous
        queryset prefetched seven relations for a serializer that has since
        stopped reading four of them.

        custom_resources is deferred down to its identifying columns so the raw
        YAML in `content` is never read out of SQLite for a list response. That
        column is the single largest thing in this table.
        """
        return queryset.select_related(
            'tenant', 'cluster', 'route_exception', 'network_policy', 'harbor_config',
        ).prefetch_related(
            'operators',
            'registry_mirrors',
            Prefetch(
                'custom_resources',
                queryset=CustomResource.objects.only('id', 'namespace_id', 'kind', 'name'),
            ),
        )


class NamespaceDetailSerializer(_NamespaceFieldsMixin, serializers.ModelSerializer):
    """Full namespace payload for the detail drawer. Shape unchanged."""
    cluster = serializers.CharField(source='cluster.name', read_only=True)
    tenant = serializers.CharField(source='tenant.name', read_only=True)
    siglum = serializers.SerializerMethodField()

    # Explicitly declare all method fields
    assigned_egress = serializers.SerializerMethodField() # <-- NEW
    provided_egress = serializers.SerializerMethodField() # <-- NEW
    network_flows = serializers.SerializerMethodField()
    routeException = serializers.SerializerMethodField()
    operators = serializers.SerializerMethodField()
    charts = serializers.SerializerMethodField()
    registry_mirrors = serializers.SerializerMethodField()
    templates = serializers.SerializerMethodField()
    resourceQuota = serializers.SerializerMethodField()
    harbor = serializers.SerializerMethodField()
    gpu = serializers.SerializerMethodField()
    owners = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()
    robotAccounts = serializers.SerializerMethodField()

    class Meta:
        model = Namespace
        fields = [
            'name', 'tenant', 'cluster', 'siglum', 'lifecycle', 'is_devspace', 'is_cso',
            'devspace_user', 'request_ticket', 'is_decommissioned',
            'assigned_egress', 'provided_egress', 'network_flows', 'routeException', 'operators', 'charts',
            'registry_mirrors', 'templates', 'resourceQuota', 'harbor', 'gpu',
            'owners', 'users', 'robotAccounts'
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_assigned_egress(self, obj):
        if obj.egress_router and getattr(obj.egress_router, 'egress_ips', None):
            ips = obj.egress_router.egress_ips
            return {
                "name": obj.egress_router.name,
                "ip": ips[0] if isinstance(ips, list) and len(ips) > 0 else ips
            }
        return None

    @extend_schema_field(OpenApiTypes.ANY)
    def get_provided_egress(self, obj):
        if getattr(obj, 'is_cso', False):
            routers = obj.provided_routers.all()
            return [{"name": r.name, "ips": r.egress_ips if isinstance(r.egress_ips, list) else [r.egress_ips]} for r in routers]
        return []

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_network_flows(self, obj):
        np = getattr(obj, 'network_policy', None)
        
        connections = []
        for conn in obj.network_connections.all():
            connections.append({
                "from": conn.from_pod,
                "to": conn.to_destinations,
                "flows": conn.flows
            })
            
        return {
            "enabled": np.flows_enabled if np else False,
            "dns": np.dns_resolution_enabled if np else False,
            "proxy": np.proxy_enabled if np else False,
            "connections": connections
        }

    @extend_schema_field(OpenApiTypes.ANY)
    def get_charts(self, obj):
        return [{"name": h.chart_name, "version": h.version} for h in obj.helm_deployments.all()]

    @extend_schema_field(OpenApiTypes.ANY)
    def get_templates(self, obj):
        return [{"kind": c.kind, "name": c.name, "content": c.content} for c in obj.custom_resources.all()]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_resourceQuota(self, obj):
        rq = getattr(obj, 'resource_quota', None)
        if not rq: return {"enabled": False}
        return {
            "enabled": True, "requestsCpu": rq.requests_cpu, "limitsCpu": rq.limits_cpu,
            "requestsMemory": rq.requests_memory, "limitsMemory": rq.limits_memory
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_gpu(self, obj):
        g = getattr(obj, 'gpu_allocation', None)
        if not g: return None
        return {"tier": g.gpu_tier, "type": g.allocation_type, "count": g.gpu_count}

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_owners(self, obj):
        return [ua.email for ua in obj.user_accesses.all() if ua.role == 'Owner']

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_users(self, obj):
        return [ua.email for ua in obj.user_accesses.all() if ua.role == 'User']

    @extend_schema_field(OpenApiTypes.ANY)
    def get_robotAccounts(self, obj):
        return [{"nameSuffix": r.name_suffix, "default": r.is_default, "permissions": r.permissions} for r in obj.robot_accounts.all()]


# Back-compat alias. The detail shape is what the old name always produced, so
# any importer that has not been updated keeps its current behaviour. Remove
# once the API layer split (§5) has moved every caller.
NamespaceSerializer = NamespaceDetailSerializer