"""Cluster and tenant viewsets."""
from django.db.models import Count, Q
from drf_spectacular.utils import (
    OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view,
)
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from dashboard.api.filters import TenantFilter
from dashboard.api.pagination import StandardResultsSetPagination
from dashboard.models import Cluster, Tenant
from dashboard.serializers import (
    ClusterSerializer, TenantDetailSerializer, TenantSerializer,
)


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
