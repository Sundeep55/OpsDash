"""Siglum search across namespaces and tenants."""
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import Namespace, Tenant, effective_siglum_expr
from dashboard.serializers import NamespaceListSerializer, TenantSerializer


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
