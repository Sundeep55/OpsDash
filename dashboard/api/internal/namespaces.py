"""Namespace viewset: trimmed payload for list, full payload for detail."""
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from dashboard.api.filters import NamespaceFilter
from dashboard.api.pagination import StandardResultsSetPagination
from dashboard.models import Namespace
from dashboard.serializers import NamespaceDetailSerializer, NamespaceListSerializer


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
