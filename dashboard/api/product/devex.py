"""Developer experience: devspaces and per-namespace rosters."""
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import Namespace
from dashboard.serializers import DevSpaceFlatSerializer, ProjectRosterSerializer
from .auth import ProductApiAuthMixin


class DevExDevspaceApiView(ProductApiAuthMixin, APIView):
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


class DevExRosterApiView(ProductApiAuthMixin, APIView):
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
