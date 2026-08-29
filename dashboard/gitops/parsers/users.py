"""Access lists, from the provisioner's project_*_config blocks.

Namespaces and capsules carry the same two blocks and are treated the same way,
which is the point: a capsule's members are people with access to part of the
estate, and the Users directory should say so.
"""
from dashboard.models import UserAccess


def _initial_users(config, outer_key, inner_key):
    outer = config.get(outer_key) or {}
    inner = outer.get(inner_key) or {}
    return inner.get('initialUsers') or []


def read_access_lists(config):
    """(owners, users) as declared, for callers that only want the addresses."""
    return (
        [e for e in _initial_users(config, 'project_owner_config', 'project_owner') if e],
        [e for e in _initial_users(config, 'project_user_config', 'project_users') if e],
    )


def apply_user_access(config, namespace=None, capsule=None):
    """Replace one namespace's or one capsule's access list.

    Delete-then-recreate rather than reconcile, because the YAML is a flat list
    of addresses with no stable identity to match on. This is why the per-file
    transaction matters: a failure between the delete and the inserts would
    otherwise leave the record with no users at all.
    """
    if namespace is None and capsule is None:
        raise ValueError('apply_user_access needs a namespace or a capsule')

    owners, users = read_access_lists(config)

    if namespace is not None:
        UserAccess.objects.filter(namespace=namespace).delete()
    else:
        UserAccess.objects.filter(capsule=capsule).delete()

    for email, role in [(e, 'Owner') for e in owners] + [(e, 'User') for e in users]:
        UserAccess.objects.create(
            namespace=namespace, capsule=capsule, email=email, role=role,
        )
