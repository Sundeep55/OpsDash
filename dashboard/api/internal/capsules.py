"""Capsule tenants: a delegated slice of a tenant with its own shared quota."""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.filters import SearchFilter

from dashboard.models import Capsule
from dashboard.serializers import CapsuleDetailSerializer, CapsuleSerializer


@extend_schema_view(
    get=extend_schema(
        description=(
            "Capsule tenants. A capsule is a delegated slice of a tenant whose "
            "users create their own namespaces against one shared resource "
            "quota.\n\n"
            "Those namespaces are deliberately not tracked: the estate records "
            "the capsule and its quota, and what runs inside is the capsule "
            "owner's business.\n\n"
            "`is_decommissioned=true|false` narrows by status and omitting it "
            "returns both, matching the tenant and namespace lists; `cluster` "
            "narrows to one cluster; `search` matches capsule, tenant or siglum."
        ),
    )
)
class CapsuleListApiView(generics.ListAPIView):
    serializer_class = CapsuleSerializer
    filter_backends = [SearchFilter]
    search_fields = ['name', 'tenant__name', 'siglum']

    def get_queryset(self):
        qs = Capsule.objects.select_related('tenant', 'cluster')

        cluster = self.request.query_params.get('cluster')
        if cluster and cluster != 'All':
            qs = qs.filter(cluster__name=cluster)

        # Same convention as the tenant and namespace lists rather than a
        # bespoke one: an explicit true/false narrows, and omitting it returns
        # both. This used to be `status=all`, which meant the tri-state pill
        # every other directory has could not be wired up here -- so a
        # decommissioned capsule was not reachable from the UI at all.
        decommissioned = self.request.query_params.get('is_decommissioned')
        if decommissioned in ('true', 'True', '1'):
            qs = qs.filter(is_decommissioned=True)
        elif decommissioned in ('false', 'False', '0'):
            qs = qs.filter(is_decommissioned=False)

        return qs.order_by('name')


@extend_schema_view(
    get=extend_schema(
        description=(
            "One capsule in full: its shared quota, Harbor project, owners and "
            "users, any manifests under its templates/ directory, and the rest "
            "of its provisioner block verbatim under `config`."
        ),
    )
)
class CapsuleDetailApiView(generics.RetrieveAPIView):
    serializer_class = CapsuleDetailSerializer
    lookup_field = 'name'
    lookup_url_kwarg = 'name'

    def get_queryset(self):
        return (Capsule.objects
                .select_related('tenant', 'cluster')
                .prefetch_related('custom_resources'))
