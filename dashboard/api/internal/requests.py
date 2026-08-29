"""Request tickets, and everything created or changed under each one.

Previously this read only Tenant.request_ticket, so a ticket showed the tenant
it created and nothing else -- not the namespaces, not the capsules, not the
route exception it granted. For a ticket that added a namespace to an existing
tenant it showed nothing at all, because no tenant carried that ticket.

The point of the view is "what did this ticket do", so it gathers every record
that names one.
"""
import collections

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.models import Capsule, Namespace, RouteException, Tenant

# The order entries appear under a ticket. A ticket usually creates a tenant and
# then things inside it, so that is the order it reads in.
KIND_ORDER = {'Tenant': 0, 'Namespace': 1, 'Capsule': 2, 'Route exception': 3}


class RequestTicketListView(APIView):
    @extend_schema(
        description=(
            "ITSM tickets and what each one produced. An entry's `type` is "
            "Tenant, Namespace, Capsule or Route exception; `cluster`, "
            "`tenant` and `decommissioned` are present where they apply, so "
            "the ticket can be read without opening each record."
        ),
        responses={200: OpenApiTypes.ANY},
    )
    def get(self, request):
        search = request.query_params.get('search', '').strip()
        grouped = collections.defaultdict(list)

        def add(ticket, entry):
            if ticket:
                grouped[ticket].append(entry)

        def matches(qs, field):
            qs = qs.exclude(**{f'{field}__isnull': True}).exclude(**{f'{field}__exact': ''})
            return qs.filter(**{f'{field}__icontains': search}) if search else qs

        for t in matches(Tenant.objects.select_related('cluster'), 'request_ticket'):
            add(t.request_ticket, {
                'type': 'Tenant', 'name': t.name,
                'cluster': t.cluster.name if t.cluster else None,
                'tenant': t.name,
                'decommissioned': t.is_decommissioned,
            })

        for n in matches(Namespace.objects.select_related('cluster', 'tenant'), 'request_ticket'):
            add(n.request_ticket, {
                'type': 'Namespace', 'name': n.name,
                'cluster': n.cluster.name if n.cluster else None,
                'tenant': n.tenant.name if n.tenant else None,
                'lifecycle': n.lifecycle,
                'decommissioned': n.is_decommissioned,
            })

        for c in matches(Capsule.objects.select_related('cluster', 'tenant'), 'request_ticket'):
            add(c.request_ticket, {
                'type': 'Capsule', 'name': c.name,
                'cluster': c.cluster.name if c.cluster else None,
                'tenant': c.tenant.name if c.tenant else None,
                'lifecycle': c.lifecycle,
                'decommissioned': c.is_decommissioned,
            })

        # A route exception is granted under its own ticket, separate from the
        # one that created the namespace. Without it a security ticket resolved
        # to nothing at all.
        for e in matches(
            RouteException.objects.select_related('namespace', 'namespace__cluster',
                                                  'namespace__tenant'),
            'request_id',
        ):
            ns = e.namespace
            add(e.request_id, {
                'type': 'Route exception',
                'name': ns.name if ns else '(namespace removed)',
                'cluster': ns.cluster.name if ns and ns.cluster else None,
                'tenant': ns.tenant.name if ns and ns.tenant else None,
                'status': e.status,
                'expires_at': e.effective_expires_at,
                'decommissioned': ns.is_decommissioned if ns else False,
            })

        payload = []
        for ticket, entries in grouped.items():
            entries.sort(key=lambda e: (KIND_ORDER.get(e['type'], 9), e['name']))
            payload.append({
                'id': ticket,
                'data': entries,
                'counts': collections.Counter(e['type'] for e in entries),
            })

        payload.sort(key=lambda t: t['id'])
        return Response(payload)
