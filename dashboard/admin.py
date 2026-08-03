from django.contrib import admin
from .models import (
    Cluster, Tenant, EgressRouter, Namespace,
    ResourceQuota, GPUAllocation,
    ServiceMeshControlPlane, NetworkPolicy, RouteException, HarborConfig,
    Operator, HelmDeployment, RegistryMirror, CustomResource,
    RobotAccount, NetworkConnection, UserAccess
)

@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'cluster', 'siglum', 'is_decommissioned')
    list_filter = ('cluster', 'is_decommissioned')
    search_fields = ('name', 'siglum', 'cost_center')

@admin.register(EgressRouter)
class EgressRouterAdmin(admin.ModelAdmin):
    list_display = ('name', 'cluster')
    search_fields = ('name', 'cluster__name')

@admin.register(Namespace)
class NamespaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'cluster', 'lifecycle', 'is_devspace', 'is_decommissioned')
    list_filter = ('cluster', 'lifecycle', 'is_devspace', 'is_decommissioned')
    search_fields = ('name', 'tenant__name')

@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ('namespace', 'name', 'is_enabled')
    list_filter = ('name', 'is_enabled', 'namespace__cluster')
    search_fields = ('namespace__name', 'name')

@admin.register(HelmDeployment)
class HelmDeploymentAdmin(admin.ModelAdmin):
    list_display = ('namespace', 'chart_name', 'version')
    list_filter = ('chart_name',)
    search_fields = ('namespace__name', 'chart_name')

@admin.register(UserAccess)
class UserAccessAdmin(admin.ModelAdmin):
    list_display = ('email', 'namespace', 'role')
    list_filter = ('role',)
    search_fields = ('email', 'namespace__name')

# Standard registrations for the One-to-One and remaining One-to-Many models
admin.site.register(ResourceQuota)
admin.site.register(GPUAllocation)
admin.site.register(ServiceMeshControlPlane)
admin.site.register(NetworkPolicy)
admin.site.register(RouteException)
admin.site.register(HarborConfig)
admin.site.register(RegistryMirror)
admin.site.register(CustomResource)
admin.site.register(RobotAccount)
admin.site.register(NetworkConnection)