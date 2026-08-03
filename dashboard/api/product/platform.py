"""Platform inventory: per-cluster capacity totals and GPU allocations."""
from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import Cluster, GPUAllocation
from dashboard.serializers import (
    GPUAllocationFlatSerializer, PlatformClusterMetricsSerializer,
)


class PlatformClusterApiView(APIView):
    @extend_schema(responses=PlatformClusterMetricsSerializer(many=True))
    def get(self, request):
        clusters = Cluster.objects.prefetch_related(
            'namespaces', 'namespaces__resource_quota', 'namespaces__gpu_allocation'
        ).annotate(
            # .count() on the prefetched managers issued a fresh query per
            # cluster and discarded the prefetch; annotate does it in one pass.
            tenant_total=Count('tenants', distinct=True),
            namespace_total=Count('namespaces', distinct=True),
        )
        data = []
        for c in clusters:
            total_cpu_req = sum(parse_cpu(ns.resource_quota.requests_cpu) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            total_cpu_lim = sum(parse_cpu(ns.resource_quota.limits_cpu) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            total_mem_req = sum(parse_mem_gi(ns.resource_quota.requests_memory) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            total_mem_lim = sum(parse_mem_gi(ns.resource_quota.limits_memory) for ns in c.namespaces.all() if hasattr(ns, 'resource_quota') and ns.resource_quota)
            
            total_gpus = sum(
                ns.gpu_allocation.gpu_count
                for ns in c.namespaces.all()
                if getattr(ns, 'gpu_allocation', None)
            )

            data.append({
                "cluster_name": c.name,
                "total_tenants": c.tenant_total,
                "total_namespaces": c.namespace_total,
                "total_cpu_requests": total_cpu_req,
                "total_cpu_limits": total_cpu_lim,
                "total_mem_requests_gb": total_mem_req,
                "total_mem_limits_gb": total_mem_lim,
                "total_gpus_allocated": total_gpus
            })
        return Response(data)


class PlatformGPUApiView(APIView):
    @extend_schema(
        responses=GPUAllocationFlatSerializer(many=True),
        description=(
            "Every namespace with a GPU allocation, from `namespace-provisioner.gpuConfig`. "
            "Namespaces whose gpuConfig is absent or disabled are omitted entirely.\n\n"
            "`allocation_type` is the requested mode (e.g. \"full\"). `gpu_count` is the "
            "number of GPUs requested. The `limit_*` fields are the per-container bounds "
            "from gpuConfig.limitRange, surfaced verbatim as declared in the repo.\n\n"
            "Unpaginated: one call returns every GPU allocation."
        ),
    )
    def get(self, request):
        gpus = GPUAllocation.objects.select_related(
            'namespace', 'namespace__cluster', 'namespace__tenant'
        ).order_by('namespace__name')
        data = [{
            "cluster": g.namespace.cluster.name,
            "namespace": g.namespace.name,
            "tenant": g.namespace.tenant.name,
            "allocation_type": g.allocation_type or "unknown",
            "gpu_count": g.gpu_count,
            "limit_min": g.limit_min,
            "limit_max": g.limit_max,
            "limit_default": g.limit_default,
            "limit_default_request": g.limit_default_request,
        } for g in gpus]
        return Response(data)
