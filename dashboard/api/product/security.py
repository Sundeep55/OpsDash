"""Security posture: route exceptions, Harbor scanning config, robot accounts."""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import Namespace, RobotAccount, RouteException
from dashboard.serializers import (
    RobotAccountFlatSerializer, RouteExceptionFlatSerializer,
    SecurityPostureFlatSerializer,
)


@extend_schema_view(
    get=extend_schema(
        description=(
            "Every namespace holding an active route exception, with the cluster and "
            "tenant it belongs to and the ticket the exception was granted under.\n\n"
            "Unpaginated: one call returns the complete set. Optional `cluster` "
            "narrows to a single cluster; `search` matches namespace name or "
            "request id. Ordered by grant date, most recent first."
        ),
    )
)
class SecurityRouteExceptionApiView(generics.ListAPIView):
    serializer_class = RouteExceptionFlatSerializer
    # The only product endpoint that used to paginate. Consumers of these
    # endpoints want one call and one complete dataset, so it now matches the
    # other twelve and returns a bare list.
    pagination_class = None
    # DjangoFilterBackend was listed with no filterset_class or filterset_fields,
    # which makes it a no-op. Dropped; `cluster` is handled in get_queryset.
    filter_backends = [SearchFilter]
    search_fields = ['namespace__name', 'request_id']

    def get_queryset(self):
        cluster = self.request.query_params.get('cluster')
        qs = (RouteException.objects
              .filter(is_active=True)
              .select_related('namespace', 'namespace__tenant', 'namespace__cluster')
              # contacts reads the owners off each namespace; without this the
              # endpoint runs one query per exception.
              .prefetch_related('namespace__user_accesses'))
        if cluster and cluster != 'All':
            qs = qs.filter(namespace__cluster__name=cluster)

        # `status` lets a notifier ask for exactly what it needs -- typically
        # ?status=expiring for the reminder mail and ?status=expired for the
        # escalation. Filtered in Python because expiry is a derived property,
        # and the set is small (one row per exception, not per namespace).
        wanted = self.request.query_params.get('status')
        qs = qs.order_by('-granted_at')
        if wanted and wanted != 'All':
            allowed = {w.strip() for w in wanted.split(',')}
            return [r for r in qs if r.status in allowed]
        return qs


class SecurityPostureApiView(APIView):
    # Plain APIView, so there is no pagination to disable -- it returns the full
    # list by construction, like the other flat product endpoints.

    @extend_schema(
        responses=SecurityPostureFlatSerializer(many=True),
        description=(
            "Per-namespace security posture: Harbor image-scanning configuration and "
            "outbound S3 connectivity, joined onto the namespace's cluster and tenant.\n\n"
            "`vulnerability_scanning` and `auto_sbom_generation` are only meaningful "
            "where `harbor_enabled` is true; they retain their last synced value "
            "otherwise. `cve_allowlist_count` is the number of CVEs explicitly "
            "excepted for the namespace -- any value above zero means image scanning "
            "will not block those CVEs.\n\n"
            "Unpaginated: one call returns every namespace."
        ),
    )
    def get(self, request):
        namespaces = Namespace.objects.select_related(
            'cluster', 'tenant', 'harbor_config', 'network_policy'
        ).order_by('name')

        data = []
        for ns in namespaces:
            h = getattr(ns, 'harbor_config', None)
            np = getattr(ns, 'network_policy', None)
            allowlist = (h.cve_allowlist if h else None) or []
            data.append({
                "namespace": ns.name,
                "cluster": ns.cluster.name,
                "tenant": ns.tenant.name,
                "harbor_enabled": bool(h and h.is_enabled),
                "vulnerability_scanning": bool(h and h.vulnerability_scanning),
                "auto_sbom_generation": bool(h and h.auto_sbom_generation),
                "cve_allowlist_count": len(allowlist) if isinstance(allowlist, list) else 0,
                "s3_connection_enabled": bool(np and np.s3_connection_enabled),
            })
        return Response(data)


class SecurityRobotApiView(APIView):
    @extend_schema(responses=RobotAccountFlatSerializer(many=True))
    def get(self, request):
        robots = RobotAccount.objects.select_related('namespace')
        data = [{
            "namespace": r.namespace.name,
            "account_name": r.name_suffix,
            "is_default": r.is_default,
            "permissions_count": len(r.permissions) if isinstance(r.permissions, list) else 0
        } for r in robots]
        return Response(data)
