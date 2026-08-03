"""Path -> (cluster, tenant, namespace) resolution over the GitOps tree.

The repository is laid out as:

    <cluster>/<tenant>/tenant-metadata.yaml
    <cluster>/<tenant>/<namespace>/values.yaml
    <cluster>/<tenant>/<namespace>/Chart.yaml
    <cluster>/<tenant>/<namespace>/templates/*.yaml
    <cluster>/.decommissioned_tenants/<tenant>/...
    <cluster>/<tenant>/.decommissioned_namespaces/<namespace>_<date>/...

Path parsing here is pure and does no database work; ensure_records() does the
writes. Keeping them apart makes the layout rules readable on their own.
"""
import os
from dataclasses import dataclass

from dashboard.models import Cluster, Namespace, Tenant

# Not a per-namespace config file: a cluster-wide pool definition that would
# otherwise be parsed as though it belonged to whatever tenant directory it sits in.
SKIP_FILENAMES = {'egressip-pool.yaml'}

YAML_SUFFIXES = ('.yaml', '.yml')

DECOMMISSIONED_TENANTS_DIR = '.decommissioned_tenants'
DECOMMISSIONED_NAMESPACES_DIR = '.decommissioned_namespaces'


@dataclass(frozen=True)
class FileLocation:
    """Where a YAML file sits in the tree, and what it therefore describes."""

    full_path: str
    filename: str
    path_parts: tuple
    cluster_name: str
    tenant_name: str
    namespace_name: str | None
    is_tenant_decommissioned: bool
    is_namespace_decommissioned: bool

    @property
    def is_template(self):
        return 'templates' in self.path_parts


def locate(full_path, rel_path):
    """Resolve a repo-relative path to a FileLocation, or None if it is not one.

    Returns None for files too shallow to identify a tenant, which is how
    top-level repo files (README, CI config) are ignored.
    """
    path_parts = tuple(rel_path.split('/'))
    if len(path_parts) < 2:
        return None

    cluster_name = path_parts[0]
    is_tenant_decomm = path_parts[1] == DECOMMISSIONED_TENANTS_DIR

    if is_tenant_decomm:
        if len(path_parts) < 3:
            return None
        tenant_name = path_parts[2]
        ns_idx = 3
    else:
        tenant_name = path_parts[1]
        ns_idx = 2

    # A decommissioned namespace directory is suffixed with its retirement date
    # (`<name>_<date>`), so the name is everything before the first underscore.
    is_ns_decomm = is_tenant_decomm
    namespace_name = None

    if DECOMMISSIONED_NAMESPACES_DIR in path_parts:
        is_ns_decomm = True
        idx = path_parts.index(DECOMMISSIONED_NAMESPACES_DIR) + 1
        if idx < len(path_parts) - 1:
            namespace_name = path_parts[idx].split('_')[0]
    elif len(path_parts) > ns_idx + 1:
        # Only files nested at least one level below the tenant belong to a
        # namespace; tenant-metadata.yaml sits directly in the tenant directory.
        namespace_name = path_parts[ns_idx]

    return FileLocation(
        full_path=full_path,
        filename=os.path.basename(full_path),
        path_parts=path_parts,
        cluster_name=cluster_name,
        tenant_name=tenant_name,
        namespace_name=namespace_name,
        is_tenant_decommissioned=is_tenant_decomm,
        is_namespace_decommissioned=is_ns_decomm,
    )


def iter_locations(repo_path):
    """Yield a FileLocation for every YAML file describing tenant config."""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.git')]
        for filename in files:
            if filename in SKIP_FILENAMES or not filename.endswith(YAML_SUFFIXES):
                continue

            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, repo_path).replace('\\', '/')

            location = locate(full_path, rel_path)
            if location is not None:
                yield location


def ensure_records(location, state):
    """Get-or-create the cluster, tenant and namespace a file belongs to.

    Registers them as present in Git so the prune does not remove them.
    Returns (cluster, tenant, namespace); namespace is None for tenant-level files.
    """
    cluster, _ = Cluster.objects.get_or_create(name=location.cluster_name)
    tenant, _ = Tenant.objects.get_or_create(
        name=location.tenant_name,
        defaults={'cluster': cluster, 'is_decommissioned': location.is_tenant_decommissioned},
    )
    state.active_tenant_names.add(tenant.name)

    if location.is_tenant_decommissioned and not tenant.is_decommissioned:
        tenant.is_decommissioned = True
        tenant.save()

    namespace = None
    if location.namespace_name:
        namespace, _ = Namespace.objects.get_or_create(
            name=location.namespace_name,
            defaults={
                'tenant': tenant,
                'cluster': cluster,
                'is_decommissioned': location.is_namespace_decommissioned,
            },
        )
        state.record_namespace(namespace.name)

        if location.is_namespace_decommissioned and not namespace.is_decommissioned:
            namespace.is_decommissioned = True
            namespace.save()

    return cluster, tenant, namespace


def read_text(path):
    """Read a file, returning None if it cannot be read or is empty."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            content = fh.read()
    except OSError:
        return None
    return content or None
