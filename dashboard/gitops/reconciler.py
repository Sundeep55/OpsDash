"""Garbage collection of records no longer present in Git.

Runs only after a complete walk. Anything the walk did not register in SyncState
is absent from the repository and gets deleted, which is what makes the database
a pure projection of Git rather than an accumulating log.
"""
import logging
from dataclasses import dataclass

from dashboard.models import Capsule, CustomResource, HelmDeployment, Namespace, Operator, Tenant

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    custom_resources: int = 0
    helm_deployments: int = 0
    operators: int = 0
    namespaces: int = 0
    capsules: int = 0
    tenants: int = 0

    @property
    def total(self):
        return (self.custom_resources + self.helm_deployments + self.operators
                + self.namespaces + self.capsules + self.tenants)

    def __str__(self):
        return (f"{self.custom_resources} CRs, {self.helm_deployments} Charts, "
                f"{self.operators} Operators, {self.namespaces} Namespaces, "
                f"{self.capsules} Capsules, {self.tenants} Tenants")


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
    operator_result = Operator.objects.exclude(id__in=state.active_operator_ids).delete()
    ns_result = Namespace.objects.exclude(name__in=state.active_namespace_names).delete()
    # Swept on its own list. A capsule is absent from active_namespace_names by
    # construction, so the namespace sweep above must not be allowed to see it.
    capsule_result = Capsule.objects.exclude(name__in=state.active_capsule_names).delete()
    tenant_result = Tenant.objects.exclude(name__in=state.active_tenant_names).delete()

    return PruneResult(
        custom_resources=_deleted_count(cr_result, CustomResource),
        helm_deployments=_deleted_count(helm_result, HelmDeployment),
        operators=_deleted_count(operator_result, Operator),
        namespaces=_deleted_count(ns_result, Namespace),
        capsules=_deleted_count(capsule_result, Capsule),
        tenants=_deleted_count(tenant_result, Tenant),
    )
