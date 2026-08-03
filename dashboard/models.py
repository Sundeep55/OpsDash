from datetime import timedelta

from django.db import models
from django.db.models import Q, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone

# A sync that has held the lock longer than this is assumed dead (OOM-killed,
# container restarted, network wedge) and may be claimed by the next caller.
# Comfortably above a worst-case full sync; tune if the repo grows a lot.
SYNC_STALE_AFTER = timedelta(minutes=30)


class SyncAlreadyRunning(RuntimeError):
    """Raised by sync_gitops when another sync already holds the lock."""


class Cluster(models.Model):
    name = models.CharField(max_length=255, primary_key=True)

    def __str__(self):
        return self.name

class Tenant(models.Model):
    name = models.CharField(max_length=255, primary_key=True)
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, related_name='tenants')
    siglum = models.CharField(max_length=50, null=True, blank=True)
    cost_center = models.CharField(max_length=100, null=True, blank=True)
    requester = models.CharField(max_length=255, null=True, blank=True)
    is_decommissioned = models.BooleanField(default=False)
    request_ticket = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.name

class EgressRouter(models.Model):
    name = models.CharField(max_length=255, primary_key=True)
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, related_name='egress_routers')
    egress_ips = models.JSONField(default=list, blank=True)
    provider_namespace = models.ForeignKey('Namespace', on_delete=models.SET_NULL, null=True, blank=True, related_name='provided_routers')

    def __str__(self):
        return self.name

class Namespace(models.Model):
    name = models.CharField(max_length=255, primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='namespaces')
    cluster = models.ForeignKey(Cluster, on_delete=models.CASCADE, related_name='namespaces')
    siglum = models.CharField(max_length=100, null=True, blank=True)
    
    lifecycle = models.CharField(max_length=50, null=True, blank=True)
    is_devspace = models.BooleanField(default=False)
    is_cso = models.BooleanField(default=False)
    devspace_user = models.EmailField(null=True, blank=True)
    egress_router = models.ForeignKey(EgressRouter, on_delete=models.SET_NULL, null=True, blank=True, related_name='routed_namespaces')
    service_mesh_cp = models.ForeignKey('ServiceMeshControlPlane', on_delete=models.SET_NULL, null=True, blank=True, related_name='data_plane_namespaces')
    request_ticket = models.CharField(max_length=100, null=True, blank=True)
    is_decommissioned = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @property
    def effective_siglum(self):
        """The siglum this namespace actually belongs to.

        A namespace can carry its own siglum, set from requiredLabels in the
        provisioner values; otherwise it inherits its tenant's. Every read path
        must resolve it through here. The namespace detail page used to apply
        the override while the dashboard org tree read ns.tenant.siglum
        directly, so an overridden namespace rendered correctly on one screen
        and wrong on the other.

        Callers should select_related('tenant') to avoid a query per row.
        """
        return self.siglum or self.tenant.siglum


def effective_siglum_expr(prefix=''):
    """SQL equivalent of Namespace.effective_siglum, for annotate()/filter().

    Lives next to the property so the two cannot drift. NullIf mirrors the
    property's `or`, which treats an empty string as absent -- plain Coalesce
    would return '' and shadow the tenant's siglum.
    """
    return Coalesce(
        NullIf(f'{prefix}siglum', Value('')),
        NullIf(f'{prefix}tenant__siglum', Value('')),
    )


# --- Compute & Resource Constraints (One-to-One) ---

class ResourceQuota(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='resource_quota')
    requests_cpu = models.CharField(max_length=50, null=True, blank=True)
    limits_cpu = models.CharField(max_length=50, null=True, blank=True)
    requests_memory = models.CharField(max_length=50, null=True, blank=True)
    limits_memory = models.CharField(max_length=50, null=True, blank=True)
    requests_storage = models.CharField(max_length=50, null=True, blank=True)

class GPUAllocation(models.Model):
    """A namespace's GPU request, from `namespace-provisioner.gpuConfig`.

    Only exists for namespaces with gpuConfig.enabled true, matching how
    ResourceQuota and HarborConfig are gated.

    There is deliberately no `gpu_tier`: the model carried one but the GitOps
    repo has no tier key. The only descriptor is gpuConfig.type ("full"), which
    is an allocation mode, so it maps to allocation_type.
    """
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='gpu_allocation')
    allocation_type = models.CharField(max_length=50, null=True, blank=True)
    gpu_count = models.IntegerField(default=0)

    # gpuConfig.limitRange -- per-container GPU bounds. Kept as strings for the
    # same reason ResourceQuota is: the repo quotes them ("0", "4") and we
    # surface them verbatim rather than guessing at units.
    limit_min = models.CharField(max_length=50, null=True, blank=True)
    limit_max = models.CharField(max_length=50, null=True, blank=True)
    limit_default = models.CharField(max_length=50, null=True, blank=True)
    limit_default_request = models.CharField(max_length=50, null=True, blank=True)

# --- Platform Services & Integrations (One-to-One) ---

class ServiceMeshControlPlane(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='is_service_mesh_cp')
    domain = models.CharField(max_length=255, null=True, blank=True)
    dataplane_namespaces = models.JSONField(default=list, blank=True)

class NetworkPolicy(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='network_policy')
    flows_enabled = models.BooleanField(default=False)
    dns_resolution_enabled = models.BooleanField(default=False)
    proxy_enabled = models.BooleanField(default=False)
    s3_connection_enabled = models.BooleanField(default=False)

# NEW: Renamed from SandboxException
class RouteException(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='route_exception')
    is_active = models.BooleanField(default=False)
    request_id = models.CharField(max_length=100, null=True, blank=True)
    granted_at = models.DateField(null=True, blank=True)

class HarborConfig(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, primary_key=True, related_name='harbor_config')
    is_enabled = models.BooleanField(default=False)
    storage_quota_gb = models.IntegerField(default=0)
    vulnerability_scanning = models.BooleanField(default=False)
    auto_sbom_generation = models.BooleanField(default=False)
    cve_allowlist = models.JSONField(default=list, null=True, blank=True)

# --- Software Stack & Communication (One-to-Many) ---

class Operator(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='operators')
    name = models.CharField(max_length=100)
    is_enabled = models.BooleanField(default=False)

class HelmDeployment(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='helm_deployments')
    chart_name = models.CharField(max_length=255)
    version = models.CharField(max_length=100, null=True, blank=True)

class RegistryMirror(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='registry_mirrors')
    name = models.CharField(max_length=255)
    endpoint_url = models.URLField(max_length=500)
    image = models.CharField(max_length=500, null=True, blank=True)
    tag = models.CharField(max_length=100, null=True, blank=True)

class CustomResource(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='custom_resources')
    kind = models.CharField(max_length=100)
    name = models.CharField(max_length=255)
    content = models.TextField()

class RobotAccount(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='robot_accounts')
    name_suffix = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    permissions = models.JSONField(default=list, blank=True)

class NetworkConnection(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='network_connections')
    from_pod = models.CharField(max_length=255)
    to_destinations = models.JSONField(default=list)
    flows = models.JSONField(default=list)

class UserAccess(models.Model):
    namespace = models.ForeignKey(Namespace, on_delete=models.CASCADE, related_name='user_accesses')
    email = models.EmailField()
    role = models.CharField(max_length=100)

# --- NEW: Shared System State for Container Syncing ---
class SystemSyncStatus(models.Model):
    """Singleton table to track background syncs across isolated containers"""
    id = models.IntegerField(primary_key=True, default=1)
    is_syncing = models.BooleanField(default=False)
    last_sync_time = models.DateTimeField(null=True, blank=True)
    last_message = models.CharField(max_length=255, default="Ready")
    sync_started_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def get_state(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    @classmethod
    def try_acquire(cls, message="Starting sync..."):
        """Atomically claim the sync lock. Returns True if this caller won it.

        Written as a single conditional UPDATE rather than read-then-write: the
        deployment runs 3 gunicorn workers plus a sidecar container, so a
        check-then-set leaves a window where two callers both see is_syncing=False
        and both start writing the same SQLite file.

        A lock older than SYNC_STALE_AFTER is treated as abandoned, so a crashed
        sync cannot wedge is_syncing=True forever.
        """
        cls.get_state()  # ensure the singleton row exists
        now = timezone.now()
        claimed = cls.objects.filter(id=1).filter(
            Q(is_syncing=False)
            | Q(sync_started_at__isnull=True)
            | Q(sync_started_at__lt=now - SYNC_STALE_AFTER)
        ).update(is_syncing=True, sync_started_at=now, last_message=message)
        return claimed == 1

    @classmethod
    def release(cls, message, completed=False):
        """Drop the lock. Only a completed run advances last_sync_time."""
        fields = {"is_syncing": False, "sync_started_at": None, "last_message": message}
        if completed:
            fields["last_sync_time"] = timezone.now()
        cls.objects.filter(id=1).update(**fields)

    @classmethod
    def set_message(cls, message):
        """Progress update. Targeted UPDATE so it cannot clobber other columns."""
        cls.objects.filter(id=1).update(last_message=message[:255])