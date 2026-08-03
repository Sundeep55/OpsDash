"""Query filters and the quantity parsers the aggregates depend on."""
from django.db.models import Q
from django_filters import rest_framework as filters

from dashboard.models import Namespace, Tenant


class NamespaceFilter(filters.FilterSet):
    has_flows = filters.BooleanFilter(field_name='network_policy__flows_enabled')
    has_dns = filters.BooleanFilter(field_name='network_policy__dns_resolution_enabled')
    has_proxy = filters.BooleanFilter(field_name='network_policy__proxy_enabled')
    has_route_exception = filters.BooleanFilter(field_name='route_exception__is_active')
    has_cve_exception = filters.BooleanFilter(method='filter_by_cve_exception')
    has_mirror = filters.BooleanFilter(field_name='registry_mirrors', lookup_expr='isnull', exclude=True)
    has_templates = filters.BooleanFilter(field_name='custom_resources', lookup_expr='isnull', exclude=True)
    operator = filters.CharFilter(method='filter_by_operator')
    chart = filters.CharFilter(method='filter_by_chart')
    lifecycle = filters.CharFilter(method='filter_by_lifecycle')

    class Meta:
        model = Namespace
        fields = ['cluster', 'tenant', 'is_devspace', 'is_decommissioned', 'is_cso']

    def filter_by_operator(self, queryset, name, value):
        return queryset.filter(operators__name=value, operators__is_enabled=True)

    def filter_by_chart(self, queryset, name, value):
        if ' (v' in value:
            try:
                chart_name, version = value.split(' (v')
                version = version.rstrip(')')
                return queryset.filter(helm_deployments__chart_name=chart_name, helm_deployments__version=version)
            except ValueError:
                return queryset.filter(helm_deployments__chart_name=value)
        return queryset.filter(helm_deployments__chart_name=value)

    def filter_by_lifecycle(self, queryset, name, value):
        if value == 'egress':
            return queryset.filter(is_cso=True)
        if value == 'unassigned':
            return queryset.filter(is_devspace=False, is_cso=False).exclude(lifecycle__iexact='prod').exclude(lifecycle__iexact='dev')
        return queryset.filter(lifecycle__iexact=value)

    def filter_by_cve_exception(self, queryset, name, value):
        if value:
            return queryset.exclude(
                Q(harbor_config__isnull=True) |
                Q(harbor_config__cve_allowlist__isnull=True) |
                Q(harbor_config__cve_allowlist=[]) |
                Q(harbor_config__cve_allowlist="")
            )
        return queryset


class TenantFilter(filters.FilterSet):
    class Meta:
        model = Tenant
        fields = ['cluster', 'is_decommissioned']


def parse_cpu(val):
    if not val: return 0
    val = str(val)
    if val.endswith('m'): return float(val[:-1]) / 1000
    try: return float(val)
    except: return 0


def parse_mem_gi(val):
    if not val: return 0
    val = str(val)
    if val.endswith('Gi'): return float(val[:-2])
    if val.endswith('Mi'): return float(val[:-2]) / 1024
    if val.endswith('G'): return float(val[:-1])
    if val.endswith('M'): return float(val[:-1]) / 1024
    try: return float(val) / (1024**3)
    except: return 0
