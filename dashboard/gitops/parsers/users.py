"""Namespace access lists, from the provisioner's project_*_config blocks."""
from dashboard.models import UserAccess


def _initial_users(config, outer_key, inner_key):
    outer = config.get(outer_key) or {}
    inner = outer.get(inner_key) or {}
    return inner.get('initialUsers') or []


def apply_user_access(prov, namespace):
    """Replace a namespace's access list from provisioner config.

    Delete-then-recreate rather than reconcile, because the YAML is a flat list
    of addresses with no stable identity to match on. This is why the per-file
    transaction matters: a failure between the delete and the inserts would
    otherwise leave the namespace with no users at all.
    """
    owners = _initial_users(prov, 'project_owner_config', 'project_owner')
    users = _initial_users(prov, 'project_user_config', 'project_users')

    UserAccess.objects.filter(namespace=namespace).delete()

    for email in owners:
        if email:
            UserAccess.objects.create(namespace=namespace, email=email, role='Owner')
    for email in users:
        if email:
            UserAccess.objects.create(namespace=namespace, email=email, role='User')
