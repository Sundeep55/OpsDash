"""A capsule's values.yaml.

A capsule tenant is a delegated slice of a tenant: its users create their own
namespaces, drawing on one shared resource quota. The estate deliberately does
not track those namespaces -- only the capsule and the quota it owns.

The file looks a lot like a namespace's, which is the problem this module and
`layout().capsule_key` exist to solve: both sit at
<cluster>/<tenant>/<name>/values.yaml and both are named dcsc-*. The block name
is the only discriminator.
"""
from ..layout import layout
from .users import apply_user_access, read_access_lists


def is_capsule_payload(payload):
    """True when this values file describes a capsule rather than a namespace.

    Checked before any record is created, so a capsule directory never produces
    a Namespace row that something else would then have to clean up.
    """
    return bool(payload) and layout().capsule_key in payload


def _label(labels, *names):
    """Label lookup that ignores the domain prefix. Same reasoning as the
    namespace parser: the chart writes dcs.<domain>/lifecycle, not lifecycle."""
    wanted = {n.lower() for n in names}
    for key, value in (labels or {}).items():
        if str(key).rsplit('/', 1)[-1].strip().lower() in wanted:
            if value not in (None, ''):
                return value
    return None


def parse_capsule_values(payload, ctx):
    capsule = ctx.capsule
    if capsule is None:
        return

    block = payload.get(layout().capsule_key) or {}

    required = block.get('requiredLabels') or {}
    additional = block.get('additionalLabels') or {}

    lifecycle = _label(required, 'lifecycle', 'env') or _label(additional, 'lifecycle', 'env')
    if lifecycle:
        capsule.lifecycle = str(lifecycle).strip().lower()

    siglum = _label(required, 'siglum')
    if siglum:
        capsule.siglum = siglum

    cost_center = _label(additional, 'cost_center')
    if cost_center:
        capsule.cost_center = cost_center

    owner = (block.get('additionalAnnotations') or {}).get('tenant_owner')
    if owner:
        capsule.requester = owner

    capsule.global_egress_ip_name = block.get('globalEgressIpName') or None

    # The shared quota is the whole point of a capsule, so it is stored verbatim
    # rather than normalised -- "16", "64Gi" and "1000Mi" all mean something
    # different and the repo is inconsistent about which it uses.
    quota = block.get('resourceQuota') or {}
    capsule.quota_enabled = bool(quota.get('enabled', False))
    capsule.limits_cpu = quota.get('limitsCpu')
    capsule.requests_cpu = quota.get('requestsCpu')
    capsule.limits_memory = quota.get('limitsMemory')
    capsule.requests_memory = quota.get('requestsMemory')
    capsule.requests_ephemeral_storage = quota.get('requestsEphemeralStorage')
    capsule.requests_storage = quota.get('requestsStorage')

    harbor = block.get('harborOnboardingConfig') or {}
    capsule.harbor_enabled = bool(harbor.get('enable', harbor.get('enabled', False)))
    try:
        capsule.harbor_storage_quota_gb = int(harbor.get('storageQuota') or 0)
    except (TypeError, ValueError):
        capsule.harbor_storage_quota_gb = 0

    # Access goes into UserAccess, the same table a namespace's members go into,
    # so the Users directory and the siglum view see capsule membership. The
    # JSON columns on Capsule are kept in step with it purely so the detail page
    # can render owners and users without a join; UserAccess is the source the
    # rest of the app queries.
    owners, users = read_access_lists(block)
    capsule.owners = owners
    capsule.users = users

    # Everything else, verbatim, for the detail page: limit ranges, retention
    # policy, network policy, allowed flows, robot accounts. Stored whole rather
    # than as columns because nothing filters on it and the capsule chart is
    # still growing keys -- see the note on Capsule.config.
    capsule.config = {
        key: value for key, value in block.items()
        # Already promoted to columns above; keeping a second copy invites the
        # two to disagree.
        if key not in ('requiredLabels', 'additionalLabels', 'additionalAnnotations',
                       'resourceQuota', 'harborOnboardingConfig', 'globalEgressIpName',
                       'project_owner_config', 'project_user_config')
    }

    capsule.save()

    # After the save: the rows point at this capsule, so it has to exist first
    # on the create path.
    apply_user_access(block, capsule=capsule)

    # Route exceptions are deliberately not modelled for capsules. They hang off
    # a Namespace, and a capsule is not one; the capsule template ships
    # routeException.enabled: false and nothing writes it yet. Adding a second
    # model and a second banner query for a case that does not occur would be
    # half-building it. request-schema.yaml offers the field, so revisit when
    # a capsule actually carries a grant.
