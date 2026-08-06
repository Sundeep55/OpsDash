"""A namespace's values.yaml.

One file can carry four independent top-level blocks, applied in this order
because later ones depend on state the earlier ones write:

    egress              this namespace provides egress IPs (a "CSO" namespace)
    namespace-provisioner   the main block: quotas, Harbor, network policy, users
    service-mesh        this namespace is a mesh control plane
    registry-config     upstream mirrors replicated into this namespace

Each block's absence is meaningful: it means the feature was removed from Git
and the corresponding records must go, rather than being left behind as ghost
state.
"""
from dashboard.models import (
    EgressRouter, NetworkConnection, NetworkPolicy, Namespace, Operator,
    RobotAccount, RouteException, ServiceMeshControlPlane, RegistryMirror,
)

from ..layout import layout
from ..sections import apply_registered_sections
from .users import apply_user_access


def _extract_lifecycle(required_labels, additional_labels):
    """Lifecycle is spelled either 'lifecycle' or 'env', in either label block."""
    return (
        required_labels.get('lifecycle')
        or required_labels.get('env')
        or additional_labels.get('lifecycle')
        or additional_labels.get('env')
    )


def parse_namespace_values(payload, ctx):
    if ctx.namespace is None:
        return

    names = layout()
    egress = payload.get(names.egress_key) or {}
    prov = payload.get(names.provisioner_key) or {}
    mesh = payload.get(names.service_mesh_key) or {}
    registry = payload.get(names.registry_config_key) or {}

    if egress:
        _apply_egress(egress, ctx)
        ctx.state.record_configured(ctx.namespace)
    else:
        _clear_egress(ctx)

    if prov:
        _apply_provisioner(prov, ctx)
        ctx.state.record_configured(ctx.namespace)

    if mesh:
        _apply_service_mesh(mesh, ctx)
        ctx.state.record_configured(ctx.namespace)
    elif prov:
        # Only clear when this file genuinely describes the namespace. A file
        # with neither block says nothing about the mesh either way.
        ServiceMeshControlPlane.objects.filter(namespace=ctx.namespace).delete()

    if registry:
        _apply_registry_config(registry, ctx)
        ctx.state.record_configured(ctx.namespace)
    else:
        RegistryMirror.objects.filter(namespace=ctx.namespace).delete()


# --------------------------------------------------------------- egress / CSO

def _apply_egress(egress, ctx):
    namespace = ctx.namespace
    namespace.is_cso = True

    required = egress.get('requiredLabels') or {}
    additional = egress.get('additionalLabels') or {}

    lifecycle = _extract_lifecycle(required, additional)
    if lifecycle:
        namespace.lifecycle = str(lifecycle).strip().lower()

    siglum = required.get('siglum')
    if siglum:
        namespace.siglum = siglum

    for resource in egress.get('egressIPResources') or []:
        name = resource.get('name')
        if not name:
            continue
        router, _ = EgressRouter.objects.get_or_create(
            name=name, defaults={'cluster': ctx.cluster}
        )
        router.egress_ips = resource.get('egressIPs') or []
        router.provider_namespace = namespace
        router.save()

    namespace.save()


def _clear_egress(ctx):
    """Drop CSO state when the egress block is gone, so a namespace that stopped
    providing egress does not keep advertising routers that no longer exist."""
    namespace = ctx.namespace
    if namespace.is_cso:
        namespace.is_cso = False
        EgressRouter.objects.filter(provider_namespace=namespace).delete()
        namespace.save()


# ------------------------------------------------------- namespace-provisioner

def _apply_provisioner(prov, ctx):
    namespace = ctx.namespace

    required = prov.get('requiredLabels') or {}
    additional = prov.get('additionalLabels') or {}
    devspace = prov.get('devspaceConfig') or {}

    lifecycle = _extract_lifecycle(required, additional)
    if lifecycle:
        namespace.lifecycle = str(lifecycle).strip().lower()

    # Defaulted to absent rather than to the stored value. Defaulting to the
    # stored value made these write-once: a namespace that stopped being a
    # devspace in Git stayed flagged as one, still showing its old owner.
    namespace.is_devspace = devspace.get('isDevspace', False)
    namespace.devspace_user = devspace.get('devspaceUser') or None

    siglum = required.get('siglum')
    if siglum:
        namespace.siglum = siglum

    egress_name = additional.get('egressip_name')
    if egress_name:
        router, _ = EgressRouter.objects.get_or_create(
            name=egress_name, defaults={'cluster': ctx.cluster}
        )
        namespace.egress_router = router

    namespace.save()

    # A namespace label is the only siglum source for tenants whose metadata
    # file omits one; never let it override a tenant that declared its own.
    if siglum and not ctx.tenant.siglum:
        ctx.tenant.siglum = siglum
        ctx.tenant.save()

    # Declarative sections come from the registry in gitops/sections.py.
    # Adding a plain config block to the chart is an entry in that list and
    # nothing else -- no parser function, no call added here.
    apply_registered_sections(prov, ctx)

    # Sections whose shape the declarative form cannot express: a list of
    # children, a dict of operators, or an ordering rule against another
    # section. Each is still named in sections.py, so that list stays the
    # complete index of what the sync understands.
    _apply_network_policy(prov, ctx)
    _apply_route_exception(prov, ctx)
    _apply_operators(prov, ctx)
    _apply_robot_accounts(prov, ctx)
    apply_user_access(prov, namespace)


def _apply_network_policy(prov, ctx):
    flows = prov.get('allowedFlows') or {}

    NetworkPolicy.objects.update_or_create(
        namespace=ctx.namespace,
        defaults={
            # 'enabled' and 'enable' are both in use in the repo.
            'flows_enabled': flows.get('enabled', flows.get('enable', False)),
            'dns_resolution_enabled': flows.get('dnsResolutionEnabled', False),
            'proxy_enabled': flows.get('proxyEnabled', False),
            's3_connection_enabled': flows.get('s3ConnectionEnabled', False),
        },
    )

    # Replaced wholesale: connections have no stable identity to reconcile on.
    NetworkConnection.objects.filter(namespace=ctx.namespace).delete()
    for conn in flows.get('connections') or []:
        destinations = conn.get('to') or []
        NetworkConnection.objects.create(
            namespace=ctx.namespace,
            from_pod=conn.get('from', ''),
            to_destinations=destinations if isinstance(destinations, list) else [destinations],
            flows=conn.get('flows') or [],
        )


def _apply_route_exception(prov, ctx):
    # tenant-metadata.yaml wins: if it granted an exception for this namespace
    # earlier in the walk, leave it alone.
    if ctx.namespace.name in ctx.state.tenant_route_exceptions:
        return

    exception = prov.get('routeException') or {}
    if exception.get('enabled'):
        RouteException.objects.update_or_create(
            namespace=ctx.namespace,
            defaults={
                'is_active': True,
                'request_id': exception.get('requestId', ''),
                'granted_at': exception.get('grantedAt'),
            },
        )
    else:
        RouteException.objects.filter(namespace=ctx.namespace).delete()


def _apply_operators(prov, ctx):
    for name, config in (prov.get('managedServices') or {}).items():
        if isinstance(config, dict):
            operator, _ = Operator.objects.update_or_create(
                namespace=ctx.namespace,
                name=name,
                defaults={'is_enabled': config.get('enabled', False)},
            )
            # Registered so the prune can drop operators removed from Git.
            # Without this an operator deleted from managedServices kept its
            # last is_enabled value forever and stayed in the analytics counts.
            ctx.state.active_operator_ids.add(operator.id)


def _apply_robot_accounts(prov, ctx):
    config = prov.get('harborRobotAccounts') or {}

    RobotAccount.objects.filter(namespace=ctx.namespace).delete()
    if not config.get('enabled'):
        return

    for account in config.get('robotAccounts') or []:
        RobotAccount.objects.create(
            namespace=ctx.namespace,
            name_suffix=account.get('nameSuffix', ''),
            is_default=account.get('default', False),
            permissions=account.get('permissions') or [],
        )


# ------------------------------------------------------------- service mesh

def _apply_service_mesh(mesh, ctx):
    cluster_config = mesh.get('cluster') or {}
    dataplane = (mesh.get('dataplane') or {}).get('namespaces') or []

    control_plane, _ = ServiceMeshControlPlane.objects.update_or_create(
        namespace=ctx.namespace,
        defaults={
            'domain': cluster_config.get('domain', ''),
            'dataplane_namespaces': dataplane if isinstance(dataplane, list) else [],
        },
    )

    member_names = []
    for entry in dataplane:
        name = entry.get('name') if isinstance(entry, dict) else str(entry)
        # 'None' appears literally in the repo where a slot is unfilled.
        if not name or name == 'None':
            continue

        member, _ = Namespace.objects.get_or_create(
            name=name, defaults={'tenant': ctx.tenant, 'cluster': ctx.cluster}
        )
        ctx.state.record_namespace(member.name)
        member.service_mesh_cp = control_plane
        member.save(update_fields=['service_mesh_cp'])
        member_names.append(member.name)

    # Detach namespaces dropped from the dataplane list. The link was only ever
    # set, so a namespace removed from the mesh in Git kept claiming membership.
    Namespace.objects.filter(service_mesh_cp=control_plane).exclude(
        name__in=member_names
    ).update(service_mesh_cp=None)


# ----------------------------------------------------------- registry-config

def _apply_registry_config(registry, ctx):
    registries = {r.get('name'): r for r in registry.get('registries') or []}
    replications = registry.get('dockerRegistryReplications') or []

    if not (replications or registries):
        return

    RegistryMirror.objects.filter(namespace=ctx.namespace).delete()

    for replication in replications:
        name = replication.get('registry')
        info = registries.get(name) or {}

        # Filters are a list of single-key dicts, one per filter type.
        image_filter = ""
        tag_filter = ""
        for entry in replication.get('filters') or []:
            if 'name' in entry:
                image_filter = entry['name']
            if 'tag' in entry:
                tag_filter = entry['tag']

        RegistryMirror.objects.create(
            namespace=ctx.namespace,
            name=name or replication.get('name', 'mirror'),
            endpoint_url=info.get('endpointUrl', ''),
            image=image_filter,
            tag=tag_filter,
        )
