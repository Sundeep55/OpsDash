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
from dashboard.models import Capsule, HelmDeployment, Namespace, Operator, Tenant

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
        # Tenants owning at least one namespace or capsule in this cluster.
        # Counted as a set rather than a running total because a tenant is
        # reached once per namespace and would otherwise be counted that often.
        "tenants": set(),
        # Capsules are counted, not resource-summed: their quota is shared
        # across namespaces the estate does not track, so adding it to the
        # namespace totals would double-count against the same allocation.
        "capsules": 0,
        "capsule_lifecycles": {"dev": 0, "prod": 0, "unassigned": 0},
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
        capsules = Capsule.objects.filter(is_decommissioned=False)
        if scoped:
            namespaces = namespaces.filter(cluster__name=cluster)
            tenants = tenants.filter(cluster__name=cluster)
            capsules = capsules.filter(cluster__name=cluster)

        analytics = {
            "global_kpis": {
                "tenants": tenants.count(),
                "namespaces": namespaces.count(),
                "capsules": capsules.count(),
                "cpu_req": 0,
                "mem_req": 0,
                # Limits alongside requests. A request is what the namespace is
                # guaranteed; a limit is what it may burst to. Showing only the
                # request told half the story -- an estate can be comfortably
                # within its requests and still be committed to twice that.
                "cpu_limit": 0,
                "mem_limit": 0,
            },
            "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0},
            "capsule_lifecycles": {"dev": 0, "prod": 0, "unassigned": 0},
            "operators": collections.defaultdict(int),
            "chart_usage": collections.defaultdict(int),
            "cluster_resources": collections.defaultdict(_empty_cluster_resources),
            "siglum_tree": {},
        }

        # Capsules are their own kind of instance and are classified like
        # namespaces are, so "how much prod is out there" counts both. They are
        # kept in a separate breakdown rather than folded into `lifecycles`,
        # because that one is a namespace count that several views total against
        # -- adding capsules to it would silently change every one of them.
        for cluster_name, tenant_name, lifecycle in (
            capsules.values_list('cluster__name', 'tenant__name', 'lifecycle')
        ):
            bucket = (lifecycle or '').strip().lower() or 'unassigned'
            if bucket not in ('dev', 'prod'):
                bucket = 'unassigned'
            per_cluster = analytics["cluster_resources"][cluster_name]
            per_cluster["capsules"] += 1
            per_cluster["capsule_lifecycles"][bucket] += 1
            analytics["capsule_lifecycles"][bucket] += 1
            # A tenant whose only presence in this cluster is a capsule still
            # counts as a tenant here.
            if tenant_name:
                per_cluster["tenants"].add(tenant_name)

        for row in namespaces.values_list(*NAMESPACE_COLUMNS).iterator():
            (cluster_name, tenant_name, ns_siglum, tenant_siglum, lifecycle,
             is_devspace, is_cso, cpu_req, cpu_limit, mem_req, mem_limit) = row

            per_cluster = analytics["cluster_resources"][cluster_name]
            per_cluster["lifecycles"]["total"] += 1

            bucket = _classify(is_cso, is_devspace, lifecycle)
            analytics["lifecycles"][bucket] += 1
            per_cluster["lifecycles"][bucket] += 1

            if tenant_name:
                per_cluster["tenants"].add(tenant_name)

            cpu_r, cpu_l = parse_cpu(cpu_req), parse_cpu(cpu_limit)
            mem_r, mem_l = parse_mem_gi(mem_req), parse_mem_gi(mem_limit)
            analytics["global_kpis"]["cpu_req"] += cpu_r
            analytics["global_kpis"]["cpu_limit"] += cpu_l
            analytics["global_kpis"]["mem_req"] += mem_r
            analytics["global_kpis"]["mem_limit"] += mem_l
            per_cluster["cpu_req"] += cpu_r
            per_cluster["cpu_limit"] += cpu_l
            per_cluster["mem_req"] += mem_r
            per_cluster["mem_limit"] += mem_l

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
            # Set -> count, the same way the siglum tree finalises its own.
            per_cluster["tenants"] = len(per_cluster["tenants"])
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
