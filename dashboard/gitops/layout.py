"""Where things live in the GitOps repository, and what they are called.

Every chart name, file name and directory name the sync depends on is declared
here rather than inline, because they differ between environments -- the names
in this repository's fixtures and documentation are stand-ins for the real
ones.

Override per environment via the GITOPS_LAYOUT setting, or per key via the
environment variables listed in ops_portal/settings.py. Nothing else needs
editing: the walker and the parsers read these.

    from .layout import layout
    layout().provisioner_key
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple

from django.conf import settings


@dataclass(frozen=True)
class Layout:
    """Names the sync matches on. All are exact matches, not patterns."""

    # --- top-level keys inside a namespace's values file ---------------------
    #: The main block: quotas, GPU, Harbor, network policy, operators, users.
    provisioner_key: str
    #: Marks a namespace that provides egress IPs.
    egress_key: str
    #: Marks a namespace that is a service-mesh control plane.
    service_mesh_key: str
    #: Upstream registry mirrors replicated into the namespace.
    registry_config_key: str

    # --- file names ----------------------------------------------------------
    #: Tenant identity and its namespace inventory, in the tenant directory.
    tenant_metadata_file: str
    #: Declares the chart's dependencies, in a namespace directory.
    chart_file: str

    # --- directory names -----------------------------------------------------
    #: Raw manifests stored verbatim rather than interpreted.
    templates_dir: str
    #: Retired tenants, directly under a cluster directory.
    decommissioned_tenants_dir: str
    #: Retired namespaces, under a tenant directory. Entries inside are
    #: suffixed with their retirement date (`<name>_<date>`).
    decommissioned_namespaces_dir: str

    #: Files to ignore outright. Cluster-wide definitions that would otherwise
    #: be parsed as though they belonged to whichever tenant directory they
    #: happen to sit in.
    skip_filenames: Tuple[str, ...]


DEFAULTS = {
    'provisioner_key': 'namespace-provisioner',
    'egress_key': 'egress',
    'service_mesh_key': 'service-mesh',
    'registry_config_key': 'registry-config',
    'tenant_metadata_file': 'tenant-metadata.yaml',
    'chart_file': 'Chart.yaml',
    'templates_dir': 'templates',
    'decommissioned_tenants_dir': '.decommissioned_tenants',
    'decommissioned_namespaces_dir': '.decommissioned_namespaces',
    'skip_filenames': ('egressip-pool.yaml',),
}


@lru_cache(maxsize=1)
def layout():
    """The resolved layout, built once per process.

    Cached because the walker consults it per file, and settings do not change
    under a running process. Call layout.cache_clear() if you override the
    setting in a test.
    """
    configured = getattr(settings, 'GITOPS_LAYOUT', None) or {}

    unknown = set(configured) - set(DEFAULTS)
    if unknown:
        # A typo here would silently leave the default in place and the sync
        # would quietly match nothing, which is very hard to diagnose from the
        # outside.
        raise ValueError(
            f"GITOPS_LAYOUT has unknown key(s): {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(DEFAULTS))}"
        )

    merged = {**DEFAULTS, **configured}
    merged['skip_filenames'] = tuple(merged['skip_filenames'] or ())
    return Layout(**merged)
