"""Cost attribution: per-namespace quotas and unattributed spend."""
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import Namespace
from dashboard.serializers import (
    FinOpsQuotaFlatSerializer, FinOpsUnattributedSerializer,
)

from .auth import ProductApiAuthMixin


class FinOpsQuotaApiView(ProductApiAuthMixin, APIView):
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


class FinOpsUnattributedApiView(ProductApiAuthMixin, APIView):
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
