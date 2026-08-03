"""Platform inventory: per-cluster capacity totals and GPU allocations."""
from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import Cluster, GPUAllocation, Namespace
from dashboard.serializers import (
    GPUAllocationFlatSerializer, PlatformClusterMetricsSerializer,
)


class PlatformClusterApiView(APIView):
    @extend_schema(responses=PlatformClusterMetricsSerializer(many=True))
    def get(self, request):
        # Two rows out, so nothing here should be per-namespace work. The
        # quota values need Python to parse ("2000m", "16Gi"), but only the
        # strings are needed -- not 800 model instances and their relations.
        # values_list keeps this to raw tuples.
        totals = {}
        rows = Namespace.objects.values_list(
            'cluster__name',
            'resource_quota__requests_cpu',
            'resource_quota__limits_cpu',
            'resource_quota__requests_memory',
            'resource_quota__limits_memory',
            'gpu_allocation__gpu_count',
        )
        for cluster_name, cpu_req, cpu_lim, mem_req, mem_lim, gpus in rows:
            bucket = totals.setdefault(
                cluster_name,
                {'cpu_req': 0, 'cpu_lim': 0, 'mem_req': 0, 'mem_lim': 0, 'gpus': 0},
            )
            bucket['cpu_req'] += parse_cpu(cpu_req)
            bucket['cpu_lim'] += parse_cpu(cpu_lim)
            bucket['mem_req'] += parse_mem_gi(mem_req)
            bucket['mem_lim'] += parse_mem_gi(mem_lim)
            bucket['gpus'] += gpus or 0

        # Counted in two queries on purpose. Annotating both onto one queryset
        # joins two multi-valued relations at once, and SQLite has to build the
        # cartesian product of every tenant against every namespace per cluster
        # before the DISTINCTs collapse it: 67ms here versus 0.9ms as two
        # separate aggregates. The cost is invisible on a small dataset and
        # grows with the product of the two counts.
        tenant_totals = dict(
            Cluster.objects.annotate(n=Count('tenants')).values_list('name', 'n')
        )
        namespace_totals = dict(
            Cluster.objects.annotate(n=Count('namespaces')).values_list('name', 'n')
        )

        empty = {'cpu_req': 0, 'cpu_lim': 0, 'mem_req': 0, 'mem_lim': 0, 'gpus': 0}
        data = []
        for c in Cluster.objects.all():
            bucket = totals.get(c.name, empty)
            data.append({
                "cluster_name": c.name,
                "total_tenants": tenant_totals.get(c.name, 0),
                "total_namespaces": namespace_totals.get(c.name, 0),
                "total_cpu_requests": bucket['cpu_req'],
                "total_cpu_limits": bucket['cpu_lim'],
                "total_mem_requests_gb": bucket['mem_req'],
                "total_mem_limits_gb": bucket['mem_lim'],
                "total_gpus_allocated": bucket['gpus'],
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
