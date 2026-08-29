"""Siglum search across namespaces, tenants and capsules.

Capsules carry a siglum of their own and fall back to their tenant's, exactly as
namespaces do. Leaving them out meant searching for a siglum that belongs to a
capsule returned the siglum in the list and then nothing under it.
"""
from django.db.models import Q
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import Capsule, Namespace, Tenant, effective_siglum_expr
from dashboard.serializers import (CapsuleSerializer, NamespaceListSerializer,
                                   TenantSerializer)


class SiglumListView(APIView):
    @extend_schema(
        description=(
            "Siglums in use, and what carries each one. A namespace's or "
            "capsule's own siglum resolves before its tenant's, so anything "
            "with an override is listed under the siglum it actually belongs "
            "to."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        search_query = request.query_params.get('search', '').strip()
        cluster = request.query_params.get('cluster', 'All')

        ns_qs = (NamespaceListSerializer.optimize(Namespace.objects.all())
                 .annotate(eff_siglum=effective_siglum_expr())
                 .exclude(eff_siglum__isnull=True))
        t_qs = (Tenant.objects.select_related('cluster')
                .exclude(siglum__isnull=True).exclude(siglum__exact=''))
        # Same fallback the model property applies: the capsule's own siglum,
        # then its tenant's.
        c_qs = (Capsule.objects.select_related('tenant', 'cluster')
                .filter(Q(siglum__isnull=False, siglum__gt='')
                        | Q(tenant__siglum__isnull=False, tenant__siglum__gt='')))

        if cluster != 'All':
            ns_qs = ns_qs.filter(cluster__name=cluster)
            t_qs = t_qs.filter(cluster__name=cluster)
            c_qs = c_qs.filter(cluster__name=cluster)

        if search_query:
            ns_qs = ns_qs.filter(eff_siglum__icontains=search_query)
            t_qs = t_qs.filter(siglum__icontains=search_query)
            c_qs = c_qs.filter(Q(siglum__icontains=search_query)
                               | Q(siglum__isnull=True, tenant__siglum__icontains=search_query)
                               | Q(siglum__exact='', tenant__siglum__icontains=search_query))

        capsules = list(c_qs[:50])

        unique = (
            set(ns_qs.values_list('eff_siglum', flat=True))
            | set(t_qs.values_list('siglum', flat=True))
            # effective_siglum is a property, so this one is resolved in Python.
            # Capsules number in the dozens, not the hundreds, so the cost is
            # not worth a second annotated expression to keep in step.
            | {c.effective_siglum for c in c_qs if c.effective_siglum}
        )

        return Response({
            "siglums": sorted(unique),
            "namespaces": NamespaceListSerializer(ns_qs[:50], many=True).data,
            "tenants": TenantSerializer(t_qs[:50], many=True).data,
            "capsules": CapsuleSerializer(capsules, many=True).data,
        })
