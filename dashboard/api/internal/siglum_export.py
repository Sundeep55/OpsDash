"""CSV export of siglum holdings.

Two shapes, because there are two questions:

    (no siglum)     one row per siglum -- how much of the platform each holds.
    ?siglum=ABDEF   one row per object under that siglum.

Namespaces and capsules are counted separately at every lifecycle. A shared
"prod: 12" column cannot be acted on: it hides whether that is twelve namespaces
or a capsule holding an unknown number of them, and those are different
conversations with different people.

Row building is shared with the other directory exports -- see exports.py.
"""
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.views import APIView

from dashboard.models import Capsule, Namespace, Tenant

from .exports import (CAPSULE_COLUMNS, NAMESPACE_COLUMNS, _blank_counts, _fold,
                      _round, _scope, capsule_row, csv_response, namespace_row)

DETAIL_COLUMNS = [
    'siglum', 'type', 'name', 'tenant', 'cluster', 'lifecycle', 'status',
    'cost_center', 'cpu_requested_cores', 'cpu_limit_cores',
    'memory_requested_gb', 'memory_limit_gb', 'request_ticket', 'requester',
]

SUMMARY_COLUMNS = [
    'siglum', 'tenants', 'objects_total',
    'namespaces_total', 'namespaces_prod', 'namespaces_dev',
    'namespaces_devspace', 'namespaces_other',
    'capsules_total', 'capsules_prod', 'capsules_dev', 'capsules_other',
    'cpu_requested_cores', 'cpu_limit_cores',
    'memory_requested_gb', 'memory_limit_gb', 'clusters',
]


def _as_detail(row, kind, name_key):
    """One namespace/capsule row reshaped into the flat per-object export."""
    out = {k: row.get(k, '') for k in DETAIL_COLUMNS}
    out['type'] = kind
    out['name'] = row[name_key]
    return out


class SiglumExportView(APIView):
    @extend_schema(
        description=(
            "Siglum holdings as CSV.\n\n"
            "`siglum=ABDEF` gives one row per tenant, namespace and capsule "
            "under it. Omit it for one row per siglum. `cluster` narrows "
            "either; `status=all` includes decommissioned records.\n\n"
            "Resource columns are reserved in Git, not measured usage."
        ),
        parameters=[
            OpenApiParameter('siglum', OpenApiTypes.STR),
            OpenApiParameter('cluster', OpenApiTypes.STR),
            OpenApiParameter('status', OpenApiTypes.STR),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        siglum = (request.query_params.get('siglum') or '').strip()

        namespaces = _scope(request, Namespace.objects.select_related(
            'tenant', 'cluster', 'resource_quota',
        ).prefetch_related('user_accesses'))
        capsules = _scope(request, Capsule.objects.select_related('tenant', 'cluster'))
        tenants = _scope(request, Tenant.objects.select_related('cluster'))

        ns_rows = [namespace_row(n) for n in namespaces]
        cap_rows = [capsule_row(c) for c in capsules]

        if siglum:
            return self._detail(siglum.upper(), ns_rows, cap_rows, tenants)
        return self._summary(ns_rows, cap_rows, tenants)

    def _detail(self, wanted, ns_rows, cap_rows, tenants):
        rows = [_as_detail(r, 'Namespace', 'namespace')
                for r in ns_rows if (r['siglum'] or '').upper() == wanted]
        rows += [_as_detail(r, 'Capsule', 'capsule')
                 for r in cap_rows if (r['siglum'] or '').upper() == wanted]

        # Tenants too, so the export shows the tenant a namespace sits under
        # even when that tenant holds nothing else under this siglum.
        for tenant in tenants:
            if (tenant.siglum or '').upper() == wanted:
                rows.append({
                    'siglum': tenant.siglum or '', 'type': 'Tenant', 'name': tenant.name,
                    'tenant': tenant.name,
                    'cluster': tenant.cluster.name if tenant.cluster else '',
                    'lifecycle': '',
                    'status': 'decommissioned' if tenant.is_decommissioned else 'active',
                    'cost_center': tenant.cost_center or '',
                    'cpu_requested_cores': 0, 'cpu_limit_cores': 0,
                    'memory_requested_gb': 0, 'memory_limit_gb': 0,
                    'request_ticket': tenant.request_ticket or '',
                    'requester': tenant.requester or '',
                })

        order = {'Tenant': 0, 'Namespace': 1, 'Capsule': 2}
        rows.sort(key=lambda r: (order.get(r['type'], 9), r['name']))
        return csv_response(f'siglum-{wanted}.csv', DETAIL_COLUMNS, rows)

    def _summary(self, ns_rows, cap_rows, tenants):
        buckets = {}

        def bucket(name):
            if name not in buckets:
                buckets[name] = {'siglum': name, 'tenants': set(),
                                 'clusters': set(), **_blank_counts()}
            return buckets[name]

        for rows, kind in ((ns_rows, 'namespaces'), (cap_rows, 'capsules')):
            for row in rows:
                name = (row['siglum'] or '').upper()
                if not name:
                    continue
                entry = bucket(name)
                _fold(entry, row, kind)
                if row['tenant']:
                    entry['tenants'].add(row['tenant'])
                if row['cluster']:
                    entry['clusters'].add(row['cluster'])

        # A tenant whose siglum nothing else carries still holds one.
        for tenant in tenants:
            name = (tenant.siglum or '').upper()
            if name:
                entry = bucket(name)
                entry['tenants'].add(tenant.name)
                if tenant.cluster:
                    entry['clusters'].add(tenant.cluster.name)

        out = []
        for entry in buckets.values():
            entry['objects_total'] = entry['namespaces_total'] + entry['capsules_total']
            entry['tenants'] = len(entry['tenants'])
            entry['clusters'] = ' '.join(sorted(entry['clusters']))
            out.append(_round(entry))
        out.sort(key=lambda e: e['siglum'])
        return csv_response('siglums-summary.csv', SUMMARY_COLUMNS, out)
