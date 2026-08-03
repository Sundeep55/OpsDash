"""tenant-metadata.yaml -- tenant identity plus its namespace inventory.

This file is the tenant's own declaration of which namespaces it owns, and it
carries route exceptions that take precedence over anything the namespace's own
values.yaml says.
"""
from dashboard.models import Namespace, RegistryMirror, RouteException

# Key spellings that have accumulated across the repo for the same field.
TENANT_TICKET_KEYS = ('tenant_request_ticket', 'req_id', 'request_ticket')
NAMESPACE_TICKET_KEYS = ('namespace_request_ticket', 'req_id', 'request_ticket')
COST_CENTER_KEYS = ('billing_code', 'wbs')


def _first(mapping, keys, default=None):
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def parse_tenant_metadata(payload, ctx):
    tenant = ctx.tenant

    tenant.siglum = payload.get('siglum', tenant.siglum)
    tenant.cost_center = _first(payload, COST_CENTER_KEYS, tenant.cost_center)
    tenant.requester = payload.get('requester', tenant.requester)

    ticket = _first(payload, TENANT_TICKET_KEYS)
    if ticket:
        tenant.request_ticket = ticket

    tenant.save()

    _apply_active_namespaces(payload.get('active_namespaces') or [], ctx)
    _apply_decommissioned_namespaces(payload.get('decommissioned_namespaces') or [], ctx)
    _apply_registry_mirrors(payload.get('active_registry_mirrors') or [], ctx)


def _get_or_create_namespace(name, ctx):
    namespace, _ = Namespace.objects.get_or_create(
        name=name, defaults={'tenant': ctx.tenant, 'cluster': ctx.cluster}
    )
    ctx.state.record_namespace(namespace.name)
    return namespace


def _apply_active_namespaces(entries, ctx):
    for entry in entries:
        name = entry.get('name')
        if not name:
            continue

        namespace = _get_or_create_namespace(name, ctx)

        ticket = _first(entry, NAMESPACE_TICKET_KEYS)
        if ticket:
            namespace.request_ticket = ticket

        lifecycle = entry.get('lifecycle')
        if lifecycle:
            namespace.lifecycle = str(lifecycle).strip().lower()

        namespace.is_decommissioned = False
        namespace.save()

        exception = entry.get('security_exception')
        if exception:
            RouteException.objects.update_or_create(
                namespace=namespace,
                defaults={
                    'is_active': True,
                    'request_id': exception.get('request_ticket', ''),
                    'granted_at': exception.get('granted_at'),
                },
            )
            # Claim it, so the namespace's own provisioner config cannot
            # overwrite or delete this grant later in the walk.
            ctx.state.tenant_route_exceptions.add(namespace.name)


def _apply_decommissioned_namespaces(entries, ctx):
    for entry in entries:
        name = entry.get('name')
        if not name:
            continue

        namespace = _get_or_create_namespace(name, ctx)

        ticket = _first(entry, NAMESPACE_TICKET_KEYS)
        if ticket:
            namespace.request_ticket = ticket

        namespace.is_decommissioned = True
        namespace.save()


def _apply_registry_mirrors(entries, ctx):
    """Mirrors declared at tenant level but attributed to specific namespaces."""
    by_namespace = {}
    for mirror in entries:
        name = mirror.get('namespace')
        if name:
            by_namespace.setdefault(name, []).append(mirror)

    for namespace_name, mirrors in by_namespace.items():
        namespace = _get_or_create_namespace(namespace_name, ctx)

        RegistryMirror.objects.filter(namespace=namespace).delete()
        for mirror in mirrors:
            RegistryMirror.objects.create(
                namespace=namespace,
                name=mirror.get('name', 'mirror'),
                image=mirror.get('image', ''),
                endpoint_url=mirror.get('url', mirror.get('endpoint_url', '')),
            )
