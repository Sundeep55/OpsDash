"""Software stack: helm deployments and upstream registry mirrors."""
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import HelmDeployment, RegistryMirror
from dashboard.serializers import (
    HelmDeploymentFlatSerializer, RegistryMirrorFlatSerializer,
)


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
