"""Per-file parsers, one module per kind of GitOps YAML.

Every parser takes the already-loaded YAML plus a ParseContext and writes to
the database. None of them read files or catch exceptions: the caller owns the
per-file transaction and decides what a failure means.
"""
from dataclasses import dataclass
from typing import Optional

from dashboard.models import Cluster, Namespace, Tenant

from .capsule import is_capsule_payload, parse_capsule_values
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
    'is_capsule_payload',
    'parse_capsule_values',
]


@dataclass
class ParseContext:
    """Everything a parser needs beyond the YAML itself."""

    cluster: Cluster
    tenant: Tenant
    # typing.Optional, not `Namespace | None`: PEP 604 unions in an evaluated
    # annotation need Python 3.10, and this runs on 3.9.
    namespace: Optional[Namespace]
    #: Set instead of `namespace` when the file describes a capsule. The two are
    #: mutually exclusive: a values file is one or the other.
    capsule: Optional[object] = None
    state: object = None  # SyncState; untyped here to avoid a circular import
