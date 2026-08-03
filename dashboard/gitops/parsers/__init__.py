"""Per-file parsers, one module per kind of GitOps YAML.

Every parser takes the already-loaded YAML plus a ParseContext and writes to
the database. None of them read files or catch exceptions: the caller owns the
per-file transaction and decides what a failure means.
"""
from dataclasses import dataclass

from dashboard.models import Cluster, Namespace, Tenant

from .custom_resources import parse_templates
from .helm import parse_chart
from .provisioner import parse_namespace_values
from .tenant import parse_tenant_metadata

__all__ = [
    'ParseContext',
    'parse_templates',
    'parse_chart',
    'parse_namespace_values',
    'parse_tenant_metadata',
]


@dataclass
class ParseContext:
    """Everything a parser needs beyond the YAML itself."""

    cluster: Cluster
    tenant: Tenant
    namespace: Namespace | None
    state: object  # SyncState; untyped here to avoid a circular import
