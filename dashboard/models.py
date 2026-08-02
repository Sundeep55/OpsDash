from django.db import models

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
    tenant_owner = models.CharField(max_length=255, null=True, blank=True)
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

# --- Compute & Resource Constraints (One-to-One) ---

class ResourceQuota(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='resource_quota')
    requests_cpu = models.CharField(max_length=50, null=True, blank=True)
    limits_cpu = models.CharField(max_length=50, null=True, blank=True)
    requests_memory = models.CharField(max_length=50, null=True, blank=True)
    limits_memory = models.CharField(max_length=50, null=True, blank=True)
    requests_storage = models.CharField(max_length=50, null=True, blank=True)
    requests_ephemeral_storage = models.CharField(max_length=50, null=True, blank=True)

class LimitRange(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='limit_range')
    container_request_cpu = models.CharField(max_length=50, null=True, blank=True)
    container_cpu = models.CharField(max_length=50, null=True, blank=True)
    container_request_ram = models.CharField(max_length=50, null=True, blank=True)
    container_ram = models.CharField(max_length=50, null=True, blank=True)
    storage_min = models.CharField(max_length=50, null=True, blank=True)
    storage_max = models.CharField(max_length=50, null=True, blank=True)

class GPUAllocation(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='gpu_allocation')
    gpu_tier = models.CharField(max_length=100)
    allocation_type = models.CharField(max_length=50, null=True, blank=True)
    gpu_count = models.IntegerField(default=0)

# --- Platform Services & Integrations (One-to-One) ---

class ServiceMeshControlPlane(models.Model):
    namespace = models.OneToOneField(Namespace, on_delete=models.CASCADE, related_name='is_service_mesh_cp')
    domain = models.CharField(max_length=255, null=True, blank=True)
    kiali_name = models.CharField(max_length=255, null=True, blank=True)
    gateway_namespaces = models.JSONField(default=list, blank=True)
    cp_tenant = models.CharField(max_length=255, null=True, blank=True)
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
    provider_name = models.CharField(max_length=100, null=True, blank=True)
    image = models.CharField(max_length=500, null=True, blank=True)
    tag = models.CharField(max_length=100, null=True, blank=True)
    schedule = models.CharField(max_length=100, null=True, blank=True)

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
    
    @classmethod
    def get_state(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj