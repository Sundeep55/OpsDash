"""Network topology: egress routing and service mesh membership."""
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import Namespace, ServiceMeshControlPlane
from dashboard.serializers import (
    EgressRoutingFlatSerializer, ServiceMeshFlatSerializer,
)


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
