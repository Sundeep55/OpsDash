"""CSV exports, for people who work in spreadsheets rather than in this UI.

Four exports, one per directory, each in two shapes: everything currently on
screen, or one record in full. What they carry is deliberately the project
management view -- who owns it, where it is, what lifecycle it is at, what it
reserves, which ticket it came from. Operators, robot accounts, network policy
and route exceptions are all left out: they answer an operational question about
how an application is wired, which is not what these readers are deciding.

No commentary rows. An earlier version wrote a leading `# ...` line to carry a
caveat, and every spreadsheet read that as the header. The caveat now lives in
the column names instead -- `cpu_requested_cores`, `memory_requested_gb` --
which is where it survives being opened six months later.
"""
import csv
from io import StringIO

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import Capsule, Namespace, Tenant


def csv_response(filename, columns, rows):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _scope(request, queryset, cluster_path='cluster__name'):
    """Apply the filters every export shares: cluster, and active-only."""
    cluster = request.query_params.get('cluster')
    if cluster and cluster != 'All':
        queryset = queryset.filter(**{cluster_path: cluster})
    if request.query_params.get('status') != 'all':
        queryset = queryset.filter(is_decommissioned=False)
    return queryset


def _lifecycle(ns):
    if ns.is_devspace:
        return 'devspace'
    if ns.is_cso:
        return 'egress'
    return ns.lifecycle or 'unassigned'


# --------------------------------------------------------------- row builders

NAMESPACE_COLUMNS = [
    'namespace', 'tenant', 'cluster', 'siglum', 'lifecycle', 'status',
    'cost_center', 'cpu_requested_cores', 'cpu_limit_cores',
    'memory_requested_gb', 'memory_limit_gb', 'storage_requested_gb',
    'request_ticket', 'requester', 'owners',
]


def namespace_row(ns):
    quota = getattr(ns, 'resource_quota', None)
    owners = sorted({a.email for a in ns.user_accesses.all() if a.role == 'Owner'})
    return {
        'namespace': ns.name,
        'tenant': ns.tenant.name if ns.tenant else '',
        'cluster': ns.cluster.name if ns.cluster else '',
        'siglum': ns.effective_siglum or '',
        'lifecycle': _lifecycle(ns),
        'status': 'decommissioned' if ns.is_decommissioned else 'active',
        'cost_center': (ns.tenant.cost_center if ns.tenant else '') or '',
        'cpu_requested_cores': parse_cpu(quota.requests_cpu) if quota else 0,
        'cpu_limit_cores': parse_cpu(quota.limits_cpu) if quota else 0,
        'memory_requested_gb': parse_mem_gi(quota.requests_memory) if quota else 0,
        'memory_limit_gb': parse_mem_gi(quota.limits_memory) if quota else 0,
        'storage_requested_gb': parse_mem_gi(quota.requests_storage) if quota else 0,
        'request_ticket': ns.request_ticket or '',
        'requester': (ns.tenant.requester if ns.tenant else '') or '',
        'owners': ' '.join(owners),
    }


CAPSULE_COLUMNS = [
    'capsule', 'tenant', 'cluster', 'siglum', 'lifecycle', 'status',
    'cost_center', 'cpu_requested_cores', 'cpu_limit_cores',
    'memory_requested_gb', 'memory_limit_gb', 'storage_requested_gb',
    'harbor_storage_gb', 'request_ticket', 'requester', 'owners', 'users',
]


def capsule_row(capsule):
    return {
        'capsule': capsule.name,
        'tenant': capsule.tenant.name if capsule.tenant else '',
        'cluster': capsule.cluster.name if capsule.cluster else '',
        'siglum': capsule.effective_siglum or '',
        'lifecycle': capsule.lifecycle or 'unassigned',
        'status': 'decommissioned' if capsule.is_decommissioned else 'active',
        'cost_center': capsule.cost_center or '',
        'cpu_requested_cores': parse_cpu(capsule.requests_cpu),
        'cpu_limit_cores': parse_cpu(capsule.limits_cpu),
        'memory_requested_gb': parse_mem_gi(capsule.requests_memory),
        'memory_limit_gb': parse_mem_gi(capsule.limits_memory),
        'storage_requested_gb': parse_mem_gi(capsule.requests_storage),
        'harbor_storage_gb': capsule.harbor_storage_quota_gb or 0,
        'request_ticket': capsule.request_ticket or '',
        'requester': capsule.requester or '',
        'owners': ' '.join(capsule.owners or []),
        'users': ' '.join(capsule.users or []),
    }


TENANT_COLUMNS = [
    'tenant', 'cluster', 'siglum', 'status', 'cost_center', 'requester',
    'request_ticket', 'namespaces_total', 'namespaces_prod', 'namespaces_dev',
    'namespaces_devspace', 'namespaces_other', 'capsules_total',
    'capsules_prod', 'capsules_dev', 'capsules_other',
    'cpu_requested_cores', 'cpu_limit_cores', 'memory_requested_gb',
    'memory_limit_gb',
]


def _blank_counts():
    return {
        'namespaces_total': 0, 'namespaces_prod': 0, 'namespaces_dev': 0,
        'namespaces_devspace': 0, 'namespaces_other': 0,
        'capsules_total': 0, 'capsules_prod': 0, 'capsules_dev': 0,
        'capsules_other': 0,
        'cpu_requested_cores': 0.0, 'cpu_limit_cores': 0.0,
        'memory_requested_gb': 0.0, 'memory_limit_gb': 0.0,
    }


def _fold(counts, row, kind):
    """Add one namespace or capsule row into a counts dict.

    Namespaces and capsules are counted separately at every lifecycle rather
    than into shared prod/dev columns. "12 prod" across two different kinds of
    object is not a number anyone can act on -- it hides whether that is twelve
    namespaces or a capsule holding an unknown number of them.
    """
    counts[f'{kind}_total'] += 1
    lifecycle = (row['lifecycle'] or '').lower()
    if kind == 'namespaces':
        bucket = lifecycle if lifecycle in ('prod', 'dev', 'devspace') else 'other'
    else:
        bucket = lifecycle if lifecycle in ('prod', 'dev') else 'other'
    counts[f'{kind}_{bucket}'] += 1
    for column in ('cpu_requested_cores', 'cpu_limit_cores',
                   'memory_requested_gb', 'memory_limit_gb'):
        counts[column] += row[column] or 0


def _round(counts):
    for column in ('cpu_requested_cores', 'cpu_limit_cores',
                   'memory_requested_gb', 'memory_limit_gb'):
        counts[column] = round(counts[column], 2)
    return counts


# ---------------------------------------------------------------------- views

def _namespaces(request):
    return _scope(request, Namespace.objects.select_related(
        'tenant', 'cluster', 'resource_quota',
    ).prefetch_related('user_accesses'))


def _capsules(request):
    return _scope(request, Capsule.objects.select_related('tenant', 'cluster'))


SHARED_PARAMS = [
    OpenApiParameter('cluster', OpenApiTypes.STR),
    OpenApiParameter('status', OpenApiTypes.STR, description="'all' includes decommissioned"),
    OpenApiParameter('search', OpenApiTypes.STR),
]


class NamespaceExportView(APIView):
    @extend_schema(
        description=("Namespaces as CSV. `search` matches name, tenant or siglum; "
                     "`tenant` narrows to one. Resource columns are reserved in "
                     "Git, not measured usage."),
        parameters=SHARED_PARAMS + [OpenApiParameter('tenant', OpenApiTypes.STR)],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        qs = _namespaces(request)
        tenant = request.query_params.get('tenant')
        if tenant:
            qs = qs.filter(tenant__name=tenant)
        search = (request.query_params.get('search') or '').strip()
        rows = [namespace_row(n) for n in qs.order_by('name')]
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in
                    f"{r['namespace']} {r['tenant']} {r['siglum']}".lower()]
        name = f'namespaces-{tenant}.csv' if tenant else 'namespaces.csv'
        return csv_response(name, NAMESPACE_COLUMNS, rows)


class CapsuleExportView(APIView):
    @extend_schema(
        description="Capsules as CSV. Resource columns are the shared quota reserved in Git.",
        parameters=SHARED_PARAMS + [OpenApiParameter('tenant', OpenApiTypes.STR)],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        qs = _capsules(request)
        tenant = request.query_params.get('tenant')
        if tenant:
            qs = qs.filter(tenant__name=tenant)
        search = (request.query_params.get('search') or '').strip()
        rows = [capsule_row(c) for c in qs.order_by('name')]
        if search:
            needle = search.lower()
            rows = [r for r in rows if needle in
                    f"{r['capsule']} {r['tenant']} {r['siglum']}".lower()]
        name = f'capsules-{tenant}.csv' if tenant else 'capsules.csv'
        return csv_response(name, CAPSULE_COLUMNS, rows)


class TenantExportView(APIView):
    @extend_schema(
        description=("Tenants as CSV, one row each, with what they hold. Namespace "
                     "and capsule counts are separate at every lifecycle."),
        parameters=SHARED_PARAMS + [OpenApiParameter('tenant', OpenApiTypes.STR)],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        tenants = _scope(request, Tenant.objects.select_related('cluster'))
        only = request.query_params.get('tenant')
        if only:
            tenants = tenants.filter(name=only)

        holdings = {}
        for ns in _namespaces(request):
            if ns.tenant_id:
                _fold(holdings.setdefault(ns.tenant_id, _blank_counts()),
                      namespace_row(ns), 'namespaces')
        for capsule in _capsules(request):
            if capsule.tenant_id:
                _fold(holdings.setdefault(capsule.tenant_id, _blank_counts()),
                      capsule_row(capsule), 'capsules')

        rows = []
        for tenant in tenants.order_by('name'):
            counts = _round(holdings.get(tenant.name, _blank_counts()))
            rows.append({
                'tenant': tenant.name,
                'cluster': tenant.cluster.name if tenant.cluster else '',
                'siglum': tenant.siglum or '',
                'status': 'decommissioned' if tenant.is_decommissioned else 'active',
                'cost_center': tenant.cost_center or '',
                'requester': tenant.requester or '',
                'request_ticket': tenant.request_ticket or '',
                **counts,
            })

        search = (request.query_params.get('search') or '').strip().lower()
        if search:
            rows = [r for r in rows if search in
                    f"{r['tenant']} {r['siglum']} {r['cost_center']}".lower()]
        name = f'tenant-{only}.csv' if only else 'tenants.csv'
        return csv_response(name, TENANT_COLUMNS, rows)
