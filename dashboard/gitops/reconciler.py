"""Garbage collection of records no longer present in Git.

Runs only after a complete walk. Anything the walk did not register in SyncState
is absent from the repository and gets deleted, which is what makes the database
a pure projection of Git rather than an accumulating log.
"""
import logging
from dataclasses import dataclass

from dashboard.models import CustomResource, HelmDeployment, Namespace, Tenant

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    custom_resources: int = 0
    helm_deployments: int = 0
    namespaces: int = 0
    tenants: int = 0

    @property
    def total(self):
        return (self.custom_resources + self.helm_deployments
                + self.namespaces + self.tenants)

    def __str__(self):
        return (f"{self.custom_resources} CRs, {self.helm_deployments} Charts, "
                f"{self.namespaces} Namespaces, {self.tenants} Tenants")


def _deleted_count(result, model):
    """Rows of `model` removed, ignoring anything deleted by cascade.

    QuerySet.delete() returns a total across every cascaded model, so reading
    result[0] reports (for example) a tenant delete that took five namespaces
    with it as "6 tenants".
    """
    return result[1].get(model._meta.label, 0)


def prune(state):
    """Delete everything absent from the repository. Returns a PruneResult."""
    cr_result = CustomResource.objects.exclude(id__in=state.active_cr_ids).delete()
    helm_result = HelmDeployment.objects.exclude(id__in=state.active_helm_ids).delete()
    ns_result = Namespace.objects.exclude(name__in=state.active_namespace_names).delete()
    tenant_result = Tenant.objects.exclude(name__in=state.active_tenant_names).delete()

    return PruneResult(
        custom_resources=_deleted_count(cr_result, CustomResource),
        helm_deployments=_deleted_count(helm_result, HelmDeployment),
        namespaces=_deleted_count(ns_result, Namespace),
        tenants=_deleted_count(tenant_result, Tenant),
    )
