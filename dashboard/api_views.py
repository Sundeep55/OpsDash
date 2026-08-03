import collections
import logging
import threading
from rest_framework import viewsets, generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters
from django.core.management import call_command
from django.db.models import Count, Q, Sum, F
from django.db.models.functions import Lower
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiTypes, extend_schema_view, OpenApiParameter

# --- IMPORT MODELS ---
from .models import (
    Cluster, Tenant, EgressRouter, Namespace,
    ResourceQuota, LimitRange, GPUAllocation,
    ServiceMeshControlPlane, NetworkPolicy, RouteException, HarborConfig,
    Operator, HelmDeployment, RegistryMirror, CustomResource,
    RobotAccount, NetworkConnection, UserAccess, SystemSyncStatus,
    SyncAlreadyRunning, effective_siglum_expr
)

logger = logging.getLogger(__name__)

# --- IMPORT SERIALIZERS ---
from .serializers import (
    ClusterSerializer, TenantSerializer, TenantDetailSerializer,
    NamespaceListSerializer, NamespaceDetailSerializer, UserListSerializer,
    PlatformClusterMetricsSerializer, GPUAllocationFlatSerializer, FinOpsQuotaFlatSerializer,
    FinOpsUnattributedSerializer, DevSpaceFlatSerializer, ProjectRosterSerializer,
    RouteExceptionFlatSerializer, RobotAccountFlatSerializer, HelmDeploymentFlatSerializer,
    RegistryMirrorFlatSerializer, EgressRoutingFlatSerializer, ServiceMeshFlatSerializer
)

# =====================================================================
# PAGINATION & FILTERS
# =====================================================================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 2000 
    
    def get_paginated_response(self, data):
        return Response({
            'count': self.page.paginator.count,
            'total_pages': self.page.paginator.num_pages,
            'current_page': self.page.number,
            'results': data
        })

class NamespaceFilter(filters.FilterSet):
    has_flows = filters.BooleanFilter(field_name='network_policy__flows_enabled')
    has_dns = filters.BooleanFilter(field_name='network_policy__dns_resolution_enabled')
    has_proxy = filters.BooleanFilter(field_name='network_policy__proxy_enabled')
    has_route_exception = filters.BooleanFilter(field_name='route_exception__is_active')
    has_cve_exception = filters.BooleanFilter(method='filter_by_cve_exception')
    has_mirror = filters.BooleanFilter(field_name='registry_mirrors', lookup_expr='isnull', exclude=True)
    has_templates = filters.BooleanFilter(field_name='custom_resources', lookup_expr='isnull', exclude=True)
    operator = filters.CharFilter(method='filter_by_operator')
    chart = filters.CharFilter(method='filter_by_chart')
    lifecycle = filters.CharFilter(method='filter_by_lifecycle')

    class Meta:
        model = Namespace
        fields = ['cluster', 'tenant', 'is_devspace', 'is_decommissioned', 'is_cso']

    def filter_by_operator(self, queryset, name, value):
        return queryset.filter(operators__name=value, operators__is_enabled=True)

    def filter_by_chart(self, queryset, name, value):
        if ' (v' in value:
            try:
                chart_name, version = value.split(' (v')
                version = version.rstrip(')')
                return queryset.filter(helm_deployments__chart_name=chart_name, helm_deployments__version=version)
            except ValueError:
                return queryset.filter(helm_deployments__chart_name=value)
        return queryset.filter(helm_deployments__chart_name=value)

    def filter_by_lifecycle(self, queryset, name, value):
        if value == 'egress':
            return queryset.filter(is_cso=True)
        if value == 'unassigned':
            return queryset.filter(is_devspace=False, is_cso=False).exclude(lifecycle__iexact='prod').exclude(lifecycle__iexact='dev')
        return queryset.filter(lifecycle__iexact=value)

    def filter_by_cve_exception(self, queryset, name, value):
        if value:
            return queryset.exclude(
                Q(harbor_config__isnull=True) |
                Q(harbor_config__cve_allowlist__isnull=True) |
                Q(harbor_config__cve_allowlist=[]) |
                Q(harbor_config__cve_allowlist="")
            )
        return queryset

class TenantFilter(filters.FilterSet):
    class Meta:
        model = Tenant
        fields = ['cluster', 'is_decommissioned']

def parse_cpu(val):
    if not val: return 0
    val = str(val)
    if val.endswith('m'): return float(val[:-1]) / 1000
    try: return float(val)
    except: return 0

def parse_mem_gi(val):
    if not val: return 0
    val = str(val)
    if val.endswith('Gi'): return float(val[:-2])
    if val.endswith('Mi'): return float(val[:-2]) / 1024
    if val.endswith('G'): return float(val[:-1])
    if val.endswith('M'): return float(val[:-1]) / 1024
    try: return float(val) / (1024**3)
    except: return 0

# =====================================================================
# ANALYTICS & GITOPS SYNC
# =====================================================================

class GlobalAnalyticsView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        cluster = request.query_params.get('cluster')
        active_namespaces = Namespace.objects.filter(is_decommissioned=False).select_related('tenant', 'cluster', 'resource_quota').prefetch_related('operators', 'helm_deployments')
        active_tenants = Tenant.objects.filter(is_decommissioned=False)
        
        if cluster and cluster != 'All':
            active_namespaces = active_namespaces.filter(cluster__name=cluster)
            active_tenants = active_tenants.filter(cluster__name=cluster)

        def get_default_cluster_resources():
            return {
                "cpu_req": 0, "cpu_limit": 0, "mem_req": 0, "mem_limit": 0,
                "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0, "total": 0},
                "operators": collections.defaultdict(int),
                "charts": collections.defaultdict(int),
                "siglum_tree": {}
            }

        analytics = {
            "global_kpis": {
                "tenants": active_tenants.count(),
                "namespaces": active_namespaces.count(),
                "cpu_req": 0,
                "mem_req": 0
            },
            "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0},
            "operators": collections.defaultdict(int),
            "chart_usage": collections.defaultdict(int),
            "cluster_resources": collections.defaultdict(get_default_cluster_resources),
            "siglum_tree": {}
        }

        for ns in active_namespaces:
            c_name = ns.cluster.name
            cr = analytics["cluster_resources"][c_name]
            
            cr["lifecycles"]["total"] += 1
            
            if getattr(ns, 'is_cso', False): 
                analytics["lifecycles"]["egress"] += 1
                cr["lifecycles"]["egress"] += 1
            elif ns.is_devspace: 
                analytics["lifecycles"]["devspace"] += 1
                cr["lifecycles"]["devspace"] += 1
            elif ns.lifecycle and ns.lifecycle.lower() == 'prod': 
                analytics["lifecycles"]["prod"] += 1
                cr["lifecycles"]["prod"] += 1
            elif ns.lifecycle and ns.lifecycle.lower() == 'dev': 
                analytics["lifecycles"]["dev"] += 1
                cr["lifecycles"]["dev"] += 1
            else:
                analytics["lifecycles"]["unassigned"] += 1
                cr["lifecycles"]["unassigned"] += 1

            if hasattr(ns, 'resource_quota') and ns.resource_quota:
                rq = ns.resource_quota
                cpu_r = parse_cpu(rq.requests_cpu)
                cpu_l = parse_cpu(rq.limits_cpu)
                mem_r = parse_mem_gi(rq.requests_memory)
                mem_l = parse_mem_gi(rq.limits_memory)

                analytics["global_kpis"]["cpu_req"] += cpu_r
                analytics["global_kpis"]["mem_req"] += mem_r

                cr["cpu_req"] += cpu_r
                cr["cpu_limit"] += cpu_l
                cr["mem_req"] += mem_r
                cr["mem_limit"] += mem_l

            for op in ns.operators.all():
                if op.is_enabled:
                    analytics["operators"][op.name] += 1
                    cr["operators"][op.name] += 1

            for chart in ns.helm_deployments.all():
                key = f"{chart.chart_name} (v{chart.version})"
                analytics["chart_usage"][key] += 1
                cr["charts"][key] += 1

            siglum = ns.effective_siglum
            if siglum and siglum != "N/A":
                s_str = siglum.upper().strip()
                start_idx = 2 if len(s_str) >= 2 else 1
                
                current_level = analytics["siglum_tree"]
                for i in range(start_idx, len(s_str) + 1):
                    prefix = s_str[:i]
                    if prefix not in current_level:
                        current_level[prefix] = {"stats": {"tenants": set(), "ns_count": 0, "dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0}, "children": {}}
                    node = current_level[prefix]["stats"]
                    node["tenants"].add(ns.tenant.name)
                    node["ns_count"] += 1
                    
                    if getattr(ns, 'is_cso', False): node["egress"] += 1
                    elif ns.is_devspace: node["devspace"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'prod': node["prod"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'dev': node["dev"] += 1
                    else: node["unassigned"] += 1
                        
                    current_level = current_level[prefix]["children"]
                    
                c_level = cr["siglum_tree"]
                for i in range(start_idx, len(s_str) + 1):
                    prefix = s_str[:i]
                    if prefix not in c_level:
                        c_level[prefix] = {"stats": {"tenants": set(), "ns_count": 0, "dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0}, "children": {}}
                    c_node = c_level[prefix]["stats"]
                    c_node["tenants"].add(ns.tenant.name)
                    c_node["ns_count"] += 1
                    
                    if getattr(ns, 'is_cso', False): c_node["egress"] += 1
                    elif ns.is_devspace: c_node["devspace"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'prod': c_node["prod"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'dev': c_node["dev"] += 1
                    else: c_node["unassigned"] += 1
                        
                    c_level = c_level[prefix]["children"]

        analytics["operators"] = dict(sorted(analytics["operators"].items(), key=lambda item: item[1], reverse=True))
        analytics["chart_usage"] = dict(sorted(analytics["chart_usage"].items(), key=lambda item: (-item[1], item[0].lower())))
        
        def serialize_tree(tree_level):
            for prefix, node in tree_level.items():
                node["stats"]["tenants"] = len(node["stats"]["tenants"])
                serialize_tree(node["children"])
                
        serialize_tree(analytics["siglum_tree"])
        
        for c_name, cr_data in analytics["cluster_resources"].items():
            cr_data["operators"] = dict(sorted(cr_data["operators"].items(), key=lambda item: item[1], reverse=True))
            cr_data["charts"] = dict(sorted(cr_data["charts"].items(), key=lambda item: (-item[1], item[0].lower())))
            serialize_tree(cr_data["siglum_tree"])

        return Response(analytics)

# =====================================================================
# GITOPS SYNC CONTROL (NOW USING DATABASE STATE)
# =====================================================================

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


# --- Legacy unversioned aliases -------------------------------------------
# /api/sync/ and /api/sync/status/ predate the /api/v2/ prefix that everything
# else sits behind. app.js still calls the old paths and the frontend is a
# separate later pass, so both routes stay live and resolve to the same
# behaviour. Excluded from the schema so the published docs show one canonical
# path per operation rather than duplicate operationIds.
# Remove these once app.js has been moved to the v2 paths.

@extend_schema(exclude=True)
class LegacySyncStatusView(SyncStatusView):
    pass


@extend_schema(exclude=True)
class LegacyTriggerSyncView(TriggerSyncView):
    pass

# =====================================================================
# BASE LIST & DETAIL VIEWS
# =====================================================================

class UserListView(generics.ListAPIView):
    serializer_class = UserListSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter]
    search_fields = ['email']

    def get_queryset(self):
        qs = UserAccess.objects.all()
        cluster = self.request.query_params.get('cluster')
        if cluster and cluster != 'All':
            qs = qs.filter(namespace__cluster__name=cluster)
            
        return qs.annotate(lower_email=Lower('email')) \
                 .values('lower_email') \
                 .annotate(access_count=Count('namespace', distinct=True), email=F('lower_email')) \
                 .order_by('lower_email')

class UserDetailView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request, email):
        cluster = request.query_params.get('cluster')
        
        qs = UserAccess.objects.annotate(lower_email=Lower('email')) \
                               .filter(lower_email=email.lower()) \
                               .select_related('namespace', 'namespace__tenant', 'namespace__cluster')
        
        if cluster and cluster != 'All':
            qs = qs.filter(namespace__cluster__name=cluster)
            
        access_map = {}
        for access in qs:
            key = f"{access.namespace.cluster.name}-{access.namespace.tenant.name}-{access.namespace.name}"
            if key not in access_map:
                access_map[key] = {
                    "namespace": access.namespace.name,
                    "tenant": access.namespace.tenant.name,
                    "cluster": access.namespace.cluster.name,
                    "roles": set()
                }
            access_map[key]["roles"].add(access.role)
            
        merged_data = []
        for v in access_map.values():
            v['role'] = ' & '.join(sorted(list(v['roles'])))
            del v['roles']
            merged_data.append(v)
            
        merged_data.sort(key=lambda x: x['namespace'])
        return Response({"email": email, "data": merged_data})

class SiglumListView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        search_query = request.query_params.get('search', '').strip()
        cluster = request.query_params.get('cluster', 'All')

        # Resolve the namespace's own siglum before its tenant's, so a namespace
        # with an override is listed and searchable under the siglum it actually
        # belongs to rather than its tenant's.
        ns_qs = NamespaceListSerializer.optimize(Namespace.objects.all()) \
                                       .annotate(eff_siglum=effective_siglum_expr()) \
                                       .exclude(eff_siglum__isnull=True)
        t_qs = Tenant.objects.select_related('cluster').exclude(siglum__isnull=True).exclude(siglum__exact='')

        if cluster != 'All':
            ns_qs = ns_qs.filter(cluster__name=cluster)
            t_qs = t_qs.filter(cluster__name=cluster)

        if search_query:
            ns_qs = ns_qs.filter(eff_siglum__icontains=search_query)
            t_qs = t_qs.filter(siglum__icontains=search_query)

        unique_siglums = set(ns_qs.values_list('eff_siglum', flat=True)) | set(t_qs.values_list('siglum', flat=True))

        return Response({
            "siglums": sorted(list(unique_siglums)),
            "namespaces": NamespaceListSerializer(ns_qs[:50], many=True).data,
            "tenants": TenantSerializer(t_qs[:50], many=True).data
        })

class RequestTicketListView(APIView):
    @extend_schema(responses={200: OpenApiTypes.ANY})
    def get(self, request):
        search = request.query_params.get('search', '').lower()
        
        t_qs = Tenant.objects.exclude(request_ticket__isnull=True)
        if search: t_qs = t_qs.filter(request_ticket__icontains=search)
        
        res = collections.defaultdict(list)
        for t in t_qs:
            res[t.request_ticket].append({"type": "Tenant", "name": t.name})
            
        return Response([{"id": k, "data": v} for k, v in res.items()])

class ClusterViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Cluster.objects.all().order_by('name')
    serializer_class = ClusterSerializer
    lookup_field = 'name' 

@extend_schema_view(
    retrieve=extend_schema(
        parameters=[
            OpenApiParameter(name='name', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, description='Tenant Name'),
            OpenApiParameter(name='id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH, exclude=True)
        ]
    )
)
class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tenant.objects.annotate(active_ns_count=Count('namespaces', filter=Q(namespaces__is_decommissioned=False))).order_by('name')
    serializer_class = TenantSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = TenantFilter
    search_fields = ['name', 'siglum', 'cost_center']
    lookup_field = 'name'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TenantDetailSerializer
        return TenantSerializer

class NamespaceViewSet(viewsets.ReadOnlyModelViewSet):
    # Detail-shaped queryset. `list` narrows it in get_queryset() below, so the
    # table view stops joining and prefetching relations it never renders.
    queryset = Namespace.objects.select_related(
        'tenant', 'cluster', 'resource_quota', 'route_exception',
        'network_policy', 'egress_router', 'harbor_config', 'gpu_allocation'
    ).prefetch_related(
        'operators', 'helm_deployments', 'registry_mirrors',
        'network_connections', 'custom_resources', 'robot_accounts', 'user_accesses'
    ).order_by('name')

    serializer_class = NamespaceDetailSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = NamespaceFilter
    # 'siglum' as well as 'tenant__siglum': searching for an overridden siglum
    # must find the namespaces that actually carry it.
    search_fields = ['name', 'tenant__name', 'siglum', 'tenant__siglum']
    lookup_field = 'name'

    def get_serializer_class(self):
        if self.action == 'list':
            return NamespaceListSerializer
        return NamespaceDetailSerializer

    def get_queryset(self):
        if self.action == 'list':
            return NamespaceListSerializer.optimize(Namespace.objects.all()).order_by('name')
        return super().get_queryset()

# =====================================================================
# API AS A PRODUCT: SPECIALIZED FLAT ENDPOINTS
# =====================================================================

class PlatformClusterApiView(APIView):
    @extend_schema(responses=PlatformClusterMetricsSerializer(many=True))
    def get(self, request):
        clusters = Cluster.objects.prefetch_related('tenants', 'namespaces', 'namespaces__resource_quota')
        data = []
        for c in clusters:
            total_cpu_req = sum(parse_cpu(ns.resource_quota.requests_cpu) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            total_cpu_lim = sum(parse_cpu(ns.resource_quota.limits_cpu) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            total_mem_req = sum(parse_mem_gi(ns.resource_quota.requests_memory) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            total_mem_lim = sum(parse_mem_gi(ns.resource_quota.limits_memory) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            
            data.append({
                "cluster_name": c.name,
                "total_tenants": c.tenants.count(),
                "total_namespaces": c.namespaces.count(),
                "total_cpu_requests": total_cpu_req,
                "total_cpu_limits": total_cpu_lim,
                "total_mem_requests_gb": total_mem_req,
                "total_mem_limits_gb": total_mem_lim,
                "total_gpus_allocated": 0
            })
        return Response(data)

class PlatformGPUApiView(APIView):
    @extend_schema(responses=GPUAllocationFlatSerializer(many=True))
    def get(self, request):
        gpus = GPUAllocation.objects.select_related('namespace', 'namespace__cluster')
        data = [{
            "cluster": g.namespace.cluster.name,
            "namespace": g.namespace.name,
            "gpu_tier": g.gpu_tier,
            "allocation_type": g.allocation_type or "unknown",
            "gpu_count": g.gpu_count
        } for g in gpus]
        return Response(data)

class FinOpsQuotaApiView(APIView):
    @extend_schema(responses=FinOpsQuotaFlatSerializer(many=True))
    def get(self, request):
        namespaces = Namespace.objects.select_related('tenant', 'resource_quota')
        cluster_filter = request.query_params.get('cluster')
        if cluster_filter:
            namespaces = namespaces.filter(cluster__name=cluster_filter)
            
        data = []
        for ns in namespaces:
            rq = getattr(ns, 'resource_quota', None)
            data.append({
                "namespace": ns.name,
                "tenant": ns.tenant.name,
                "cost_center": ns.tenant.cost_center or "N/A",
                "siglum": ns.effective_siglum or "N/A",
                "cpu_requests": parse_cpu(rq.requests_cpu) if rq else 0,
                "cpu_limits": parse_cpu(rq.limits_cpu) if rq else 0,
                "mem_requests_gb": parse_mem_gi(rq.requests_memory) if rq else 0,
                "mem_limits_gb": parse_mem_gi(rq.limits_memory) if rq else 0,
                "storage_requests_gb": parse_mem_gi(rq.requests_storage) if rq else 0
            })
        return Response(data)

class FinOpsUnattributedApiView(APIView):
    @extend_schema(responses=FinOpsUnattributedSerializer(many=True))
    def get(self, request):
        namespaces = Namespace.objects.filter(
            Q(tenant__cost_center__isnull=True) | Q(tenant__cost_center='')
        ).select_related('tenant', 'cluster', 'resource_quota')
        
        data = []
        for ns in namespaces:
            rq = getattr(ns, 'resource_quota', None)
            data.append({
                "namespace": ns.name,
                "tenant": ns.tenant.name,
                "cluster": ns.cluster.name,
                "cpu_requests": parse_cpu(rq.requests_cpu) if rq else 0,
                "mem_requests_gb": parse_mem_gi(rq.requests_memory) if rq else 0,
                "reason": "Missing Cost Center Mapping"
            })
        return Response(data)

class DevExDevspaceApiView(APIView):
    @extend_schema(responses=DevSpaceFlatSerializer(many=True))
    def get(self, request):
        namespaces = Namespace.objects.filter(is_devspace=True).select_related('cluster', 'resource_quota')
        data = []
        for ns in namespaces:
            rq = getattr(ns, 'resource_quota', None)
            data.append({
                "namespace": ns.name,
                "devspace_user": ns.devspace_user or "Unknown",
                "cluster": ns.cluster.name,
                "cpu_requests": parse_cpu(rq.requests_cpu) if rq else 0,
                "mem_requests_gb": parse_mem_gi(rq.requests_memory) if rq else 0,
            })
        return Response(data)

class DevExRosterApiView(APIView):
    @extend_schema(responses=ProjectRosterSerializer(many=True))
    def get(self, request):
        namespaces = Namespace.objects.prefetch_related('user_accesses')
        data = []
        for ns in namespaces:
            owners = []
            users = []
            for ua in ns.user_accesses.all():
                if ua.role == 'Owner': owners.append(ua.email)
                elif ua.role == 'User': users.append(ua.email)
            data.append({
                "namespace": ns.name,
                "owners": owners,
                "users": users
            })
        return Response(data)

class SecurityRouteExceptionApiView(generics.ListAPIView):
    serializer_class = RouteExceptionFlatSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['namespace__name', 'request_id']

    def get_queryset(self):
        cluster = self.request.query_params.get('cluster')
        qs = RouteException.objects.filter(is_active=True).select_related('namespace', 'namespace__tenant', 'namespace__cluster')
        if cluster and cluster != 'All':
            qs = qs.filter(namespace__cluster__name=cluster)
        return qs.order_by('-granted_at')

class SecurityRobotApiView(APIView):
    @extend_schema(responses=RobotAccountFlatSerializer(many=True))
    def get(self, request):
        robots = RobotAccount.objects.select_related('namespace')
        data = [{
            "namespace": r.namespace.name,
            "account_name": r.name_suffix,
            "is_default": r.is_default,
            "permissions_count": len(r.permissions) if isinstance(r.permissions, list) else 0
        } for r in robots]
        return Response(data)

class StackHelmApiView(APIView):
    @extend_schema(responses=HelmDeploymentFlatSerializer(many=True))
    def get(self, request):
        charts = HelmDeployment.objects.select_related('namespace', 'namespace__cluster')
        chart_filter = request.query_params.get('chart_name')
        if chart_filter:
            charts = charts.filter(chart_name__icontains=chart_filter)
            
        data = [{
            "namespace": c.namespace.name,
            "cluster": c.namespace.cluster.name,
            "chart_name": c.chart_name,
            "version": c.version or "latest"
        } for c in charts]
        return Response(data)

class StackMirrorApiView(APIView):
    @extend_schema(responses=RegistryMirrorFlatSerializer(many=True))
    def get(self, request):
        mirrors = RegistryMirror.objects.select_related('namespace', 'namespace__cluster')
        data = [{
            "namespace": m.namespace.name,
            "cluster": m.namespace.cluster.name,
            "mirror_name": m.name,
            "endpoint_url": m.endpoint_url,
            "image": m.image or "All"
        } for m in mirrors]
        return Response(data)

class NetworkEgressApiView(APIView):
    @extend_schema(responses=EgressRoutingFlatSerializer(many=True))
    def get(self, request):
        namespaces = Namespace.objects.filter(egress_router__isnull=False).select_related('cluster', 'egress_router')
        data = [{
            "namespace": ns.name,
            "cluster": ns.cluster.name,
            "egress_router": ns.egress_router.name,
            "egress_ips": ns.egress_router.egress_ips if isinstance(ns.egress_router.egress_ips, list) else []
        } for ns in namespaces]
        return Response(data)

class NetworkServiceMeshApiView(APIView):
    @extend_schema(responses=ServiceMeshFlatSerializer(many=True))
    def get(self, request):
        meshes = ServiceMeshControlPlane.objects.select_related('namespace', 'namespace__cluster')
        data = [{
            "control_plane_namespace": m.namespace.name,
            "cluster": m.namespace.cluster.name,
            "domain": m.domain or "N/A",
            "dataplane_namespaces": m.dataplane_namespaces if isinstance(m.dataplane_namespaces, list) else []
        } for m in meshes]
        return Response(data)