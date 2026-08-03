"""Dashboard aggregates: KPIs, lifecycle counts and the siglum org tree.

Built from flat rows rather than model instances. The dashboard is the heaviest
read in the application -- it touches every active namespace -- so the cost that
matters is materialising 800 Namespace objects plus their prefetched operators
and helm deployments, not the SQL. Profiling at production scale put almost all
of the time in the ORM's row-to-object work; values_list skips it entirely.

Operator and chart usage are counted by the database, since only the totals are
ever needed, never the rows.
"""
import collections

from django.db.models import Count
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import HelmDeployment, Namespace, Operator, Tenant

# Columns pulled per active namespace. Kept as a tuple so the unpack below
# cannot drift from the query.
NAMESPACE_COLUMNS = (
    'cluster__name',
    'tenant__name',
    'siglum',
    'tenant__siglum',
    'lifecycle',
    'is_devspace',
    'is_cso',
    'resource_quota__requests_cpu',
    'resource_quota__limits_cpu',
    'resource_quota__requests_memory',
    'resource_quota__limits_memory',
)


def _empty_cluster_resources():
    return {
        "cpu_req": 0, "cpu_limit": 0, "mem_req": 0, "mem_limit": 0,
        "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0, "total": 0},
        "operators": collections.defaultdict(int),
        "charts": collections.defaultdict(int),
        "siglum_tree": {},
    }


def _empty_siglum_node():
    return {
        "stats": {"tenants": set(), "ns_count": 0, "dev": 0, "prod": 0,
                  "devspace": 0, "egress": 0, "unassigned": 0},
        "children": {},
    }


def _classify(is_cso, is_devspace, lifecycle):
    """Which lifecycle bucket a namespace falls in. First match wins."""
    if is_cso:
        return "egress"
    if is_devspace:
        return "devspace"
    if lifecycle and lifecycle.lower() == 'prod':
        return "prod"
    if lifecycle and lifecycle.lower() == 'dev':
        return "dev"
    return "unassigned"


def _add_to_tree(tree, siglum, tenant_name, bucket):
    """Record a namespace at every prefix of its siglum.

    Prefixes start at two characters: the first character alone groups too
    coarsely to be a useful drill-down level.
    """
    start = 2 if len(siglum) >= 2 else 1
    level = tree
    for i in range(start, len(siglum) + 1):
        node = level.setdefault(siglum[:i], _empty_siglum_node())
        stats = node["stats"]
        stats["tenants"].add(tenant_name)
        stats["ns_count"] += 1
        stats[bucket] += 1
        level = node["children"]


def _finalise_tree(level):
    """Replace each node's tenant set with its size, in place."""
    for node in level.values():
        node["stats"]["tenants"] = len(node["stats"]["tenants"])
        _finalise_tree(node["children"])


class GlobalAnalyticsView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        cluster = request.query_params.get('cluster')
        scoped = cluster and cluster != 'All'

        namespaces = Namespace.objects.filter(is_decommissioned=False)
        tenants = Tenant.objects.filter(is_decommissioned=False)
        if scoped:
            namespaces = namespaces.filter(cluster__name=cluster)
            tenants = tenants.filter(cluster__name=cluster)

        analytics = {
            "global_kpis": {
                "tenants": tenants.count(),
                "namespaces": namespaces.count(),
                "cpu_req": 0,
                "mem_req": 0,
            },
            "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0},
            "operators": collections.defaultdict(int),
            "chart_usage": collections.defaultdict(int),
            "cluster_resources": collections.defaultdict(_empty_cluster_resources),
            "siglum_tree": {},
        }

        for row in namespaces.values_list(*NAMESPACE_COLUMNS).iterator():
            (cluster_name, tenant_name, ns_siglum, tenant_siglum, lifecycle,
             is_devspace, is_cso, cpu_req, cpu_limit, mem_req, mem_limit) = row

            per_cluster = analytics["cluster_resources"][cluster_name]
            per_cluster["lifecycles"]["total"] += 1

            bucket = _classify(is_cso, is_devspace, lifecycle)
            analytics["lifecycles"][bucket] += 1
            per_cluster["lifecycles"][bucket] += 1

            cpu_r = parse_cpu(cpu_req)
            mem_r = parse_mem_gi(mem_req)
            analytics["global_kpis"]["cpu_req"] += cpu_r
            analytics["global_kpis"]["mem_req"] += mem_r
            per_cluster["cpu_req"] += cpu_r
            per_cluster["cpu_limit"] += parse_cpu(cpu_limit)
            per_cluster["mem_req"] += mem_r
            per_cluster["mem_limit"] += parse_mem_gi(mem_limit)

            # Same resolution as Namespace.effective_siglum, done on flat columns.
            siglum = ns_siglum or tenant_siglum
            if siglum and siglum != "N/A":
                normalised = siglum.upper().strip()
                _add_to_tree(analytics["siglum_tree"], normalised, tenant_name, bucket)
                _add_to_tree(per_cluster["siglum_tree"], normalised, tenant_name, bucket)

        self._add_operator_counts(analytics, cluster if scoped else None)
        self._add_chart_counts(analytics, cluster if scoped else None)

        analytics["operators"] = dict(
            sorted(analytics["operators"].items(), key=lambda kv: kv[1], reverse=True)
        )
        analytics["chart_usage"] = dict(
            sorted(analytics["chart_usage"].items(), key=lambda kv: (-kv[1], kv[0].lower()))
        )

        _finalise_tree(analytics["siglum_tree"])
        for per_cluster in analytics["cluster_resources"].values():
            per_cluster["operators"] = dict(
                sorted(per_cluster["operators"].items(), key=lambda kv: kv[1], reverse=True)
            )
            per_cluster["charts"] = dict(
                sorted(per_cluster["charts"].items(), key=lambda kv: (-kv[1], kv[0].lower()))
            )
            _finalise_tree(per_cluster["siglum_tree"])

        return Response(analytics)

    @staticmethod
    def _add_operator_counts(analytics, cluster):
        """Enabled operators per name, counted by the database."""
        qs = Operator.objects.filter(is_enabled=True, namespace__is_decommissioned=False)
        if cluster:
            qs = qs.filter(namespace__cluster__name=cluster)

        rows = qs.values_list('namespace__cluster__name', 'name').annotate(total=Count('id'))
        for cluster_name, name, total in rows:
            analytics["operators"][name] += total
            analytics["cluster_resources"][cluster_name]["operators"][name] += total

    @staticmethod
    def _add_chart_counts(analytics, cluster):
        """Chart usage per "<name> (v<version>)", counted by the database."""
        qs = HelmDeployment.objects.filter(namespace__is_decommissioned=False)
        if cluster:
            qs = qs.filter(namespace__cluster__name=cluster)

        rows = qs.values_list(
            'namespace__cluster__name', 'chart_name', 'version'
        ).annotate(total=Count('id'))
        for cluster_name, chart_name, version, total in rows:
            key = f"{chart_name} (v{version})"
            analytics["chart_usage"][key] += total
            analytics["cluster_resources"][cluster_name]["charts"][key] += total
