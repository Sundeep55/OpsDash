"""Serializers for the internal API, consumed by the Vue SPA.

Split from the product serializers in flat.py because the two have different
stability guarantees: these may change freely alongside the frontend, whereas
the flat ones are a contract with other teams.
"""
import json
import re

from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from dashboard.gitops.sections import auto_rendered_sections, describe
from dashboard.models import Capsule, Cluster, CustomResource, Namespace, Tenant

class _NamespaceFieldsMixin:
    """Method fields whose output is identical in the list and detail payloads."""

    @extend_schema_field(OpenApiTypes.STR)
    def get_siglum(self, obj):
        return obj.effective_siglum

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_routeException(self, obj):
        re_obj = getattr(obj, 'route_exception', None)
        if not re_obj or not re_obj.is_active:
            return {"enabled": False, "status": "inactive"}

        return {
            "enabled": True,
            "status": re_obj.status,
            "requestId": re_obj.request_id,
            "grantedAt": re_obj.granted_at,
            "expiresAt": re_obj.effective_expires_at,
            "daysActive": re_obj.days_active,
            "daysRemaining": re_obj.days_remaining,
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_operators(self, obj):
        return {op.name: {"enabled": op.is_enabled} for op in obj.operators.all()}

    @extend_schema_field(OpenApiTypes.ANY)
    def get_registry_mirrors(self, obj):
        return [{"name": m.name, "image": m.image, "tag": m.tag, "endpoint_url": m.endpoint_url} for m in obj.registry_mirrors.all()]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_harbor(self, obj):
        h = getattr(obj, 'harbor_config', None)
        return {
            "enable": h.is_enabled if h else False,
            "storageQuota": h.storage_quota_gb if h else 0,
            "cveAllowlist": h.cve_allowlist if h and h.cve_allowlist else []
        }


class NamespaceListSerializer(_NamespaceFieldsMixin, serializers.ModelSerializer):
    """Trimmed payload for every table/list view of namespaces.

    Field set is exactly what the consuming templates read, established by
    grepping them rather than guessing:

        namespaces/list.html   the namespaces table
        dashboard_tab.html     the KPI drill-down (fetches page_size=500)
        tenants/detail.html    the tenant's namespace panel
        siglums_tab.html       the siglum match list

    Two fields are deliberately narrower than their detail counterparts, because
    no list consumer reads past them:

        network_flows  omits 'connections' (only namespaces/detail.html renders
                       it), which drops the network_connections query entirely
        templates      omits 'content', the raw YAML of every custom resource --
                       every consumer here only reads templates.length

    Not built by subclassing the detail serializer: the cost is in the method
    fields, so inheriting would compute them and then throw them away.
    """
    cluster = serializers.CharField(source='cluster.name', read_only=True)
    tenant = serializers.CharField(source='tenant.name', read_only=True)

    network_flows = serializers.SerializerMethodField()
    routeException = serializers.SerializerMethodField()
    operators = serializers.SerializerMethodField()
    registry_mirrors = serializers.SerializerMethodField()
    templates = serializers.SerializerMethodField()
    harbor = serializers.SerializerMethodField()

    class Meta:
        model = Namespace
        fields = [
            'name', 'tenant', 'cluster', 'lifecycle', 'is_devspace', 'is_cso',
            'is_decommissioned', 'network_flows', 'routeException', 'operators',
            'registry_mirrors', 'templates', 'harbor',
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_network_flows(self, obj):
        np = getattr(obj, 'network_policy', None)
        return {
            "enabled": np.flows_enabled if np else False,
            "dns": np.dns_resolution_enabled if np else False,
            "proxy": np.proxy_enabled if np else False,
        }

    @extend_schema_field(OpenApiTypes.ANY)
    def get_templates(self, obj):
        return [{"kind": c.kind, "name": c.name} for c in obj.custom_resources.all()]

    @staticmethod
    def optimize(queryset):
        """Attach exactly the relations this serializer reads -- and no others.

        Kept beside the field definitions so the two cannot drift: the previous
        queryset prefetched seven relations for a serializer that has since
        stopped reading four of them.

        custom_resources is deferred down to its identifying columns so the raw
        YAML in `content` is never read out of SQLite for a list response. That
        column is the single largest thing in this table.
        """
        return queryset.select_related(
            'tenant', 'cluster', 'route_exception', 'network_policy', 'harbor_config',
        ).prefetch_related(
            'operators',
            'registry_mirrors',
            Prefetch(
                'custom_resources',
                queryset=CustomResource.objects.only('id', 'namespace_id', 'kind', 'name'),
            ),
        )


class NamespaceDetailSerializer(_NamespaceFieldsMixin, serializers.ModelSerializer):
    """Full namespace payload for the detail drawer. Shape unchanged."""
    cluster = serializers.CharField(source='cluster.name', read_only=True)
    tenant = serializers.CharField(source='tenant.name', read_only=True)
    siglum = serializers.SerializerMethodField()

    # Explicitly declare all method fields
    assigned_egress = serializers.SerializerMethodField() # <-- NEW
    provided_egress = serializers.SerializerMethodField() # <-- NEW
    network_flows = serializers.SerializerMethodField()
    routeException = serializers.SerializerMethodField()
    operators = serializers.SerializerMethodField()
    charts = serializers.SerializerMethodField()
    registry_mirrors = serializers.SerializerMethodField()
    templates = serializers.SerializerMethodField()
    resourceQuota = serializers.SerializerMethodField()
    harbor = serializers.SerializerMethodField()
    gpu = serializers.SerializerMethodField()
    owners = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()
    robotAccounts = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Namespace
        fields = [
            'name', 'tenant', 'cluster', 'siglum', 'lifecycle', 'is_devspace', 'is_cso',
            'devspace_user', 'request_ticket', 'is_decommissioned',
            'assigned_egress', 'provided_egress', 'network_flows', 'routeException', 'operators', 'charts',
            'registry_mirrors', 'templates', 'resourceQuota', 'harbor', 'gpu',
            'owners', 'users', 'robotAccounts', 'sections'
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_sections(self, obj):
        """Sections published straight from the registry.

        A declarative section marked auto_render needs no serializer field and
        no template block: it appears here, and the frontend's section registry
        renders it. The long-standing sections above keep their bespoke keys and
        markup, so nothing here changes their shape.
        """
        described = {}
        for section in auto_rendered_sections():
            instance = getattr(obj, section.model._meta.get_field('namespace').related_query_name(), None)
            payload = describe(section, instance)
            if payload is not None:
                described[section.name] = payload
        return described

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_assigned_egress(self, obj):
        if obj.egress_router and getattr(obj.egress_router, 'egress_ips', None):
            ips = obj.egress_router.egress_ips
            return {
                "name": obj.egress_router.name,
                "ip": ips[0] if isinstance(ips, list) and len(ips) > 0 else ips
            }
        return None

    @extend_schema_field(OpenApiTypes.ANY)
    def get_provided_egress(self, obj):
        if getattr(obj, 'is_cso', False):
            routers = obj.provided_routers.all()
            return [{"name": r.name, "ips": r.egress_ips if isinstance(r.egress_ips, list) else [r.egress_ips]} for r in routers]
        return []

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_network_flows(self, obj):
        np = getattr(obj, 'network_policy', None)
        
        connections = []
        for conn in obj.network_connections.all():
            connections.append({
                "from": conn.from_pod,
                "to": conn.to_destinations,
                "flows": conn.flows
            })
            
        return {
            "enabled": np.flows_enabled if np else False,
            "dns": np.dns_resolution_enabled if np else False,
            "proxy": np.proxy_enabled if np else False,
            "connections": connections
        }

    @extend_schema_field(OpenApiTypes.ANY)
    def get_charts(self, obj):
        return [{"name": h.chart_name, "version": h.version} for h in obj.helm_deployments.all()]

    @extend_schema_field(OpenApiTypes.ANY)
    def get_templates(self, obj):
        return [{"kind": c.kind, "name": c.name, "content": c.content} for c in obj.custom_resources.all()]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_resourceQuota(self, obj):
        rq = getattr(obj, 'resource_quota', None)
        if not rq: return {"enabled": False}
        return {
            "enabled": True, "requestsCpu": rq.requests_cpu, "limitsCpu": rq.limits_cpu,
            "requestsMemory": rq.requests_memory, "limitsMemory": rq.limits_memory
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_gpu(self, obj):
        g = getattr(obj, 'gpu_allocation', None)
        if not g:
            return None
        # 'tier' carries gpuConfig.type because that is the only descriptor the
        # repo provides, and it is what the detail drawer renders as its primary
        # label. The drawer's secondary 'gpu.type' line now has no source and
        # should be dropped during the frontend pass.
        return {
            "tier": g.allocation_type,
            "count": g.gpu_count,
            "limits": {
                "min": g.limit_min,
                "max": g.limit_max,
                "default": g.limit_default,
                "defaultRequest": g.limit_default_request,
            },
        }

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_owners(self, obj):
        return [ua.email for ua in obj.user_accesses.all() if ua.role == 'Owner']

    @extend_schema_field({"type": "array", "items": {"type": "string"}})
    def get_users(self, obj):
        return [ua.email for ua in obj.user_accesses.all() if ua.role == 'User']

    @extend_schema_field(OpenApiTypes.ANY)
    def get_robotAccounts(self, obj):
        return [{"nameSuffix": r.name_suffix, "default": r.is_default, "permissions": r.permissions} for r in obj.robot_accounts.all()]


# Back-compat alias. The detail shape is what the old name always produced, so
# any importer that has not been updated keeps its current behaviour. Remove
# once the API layer split (§5) has moved every caller.
NamespaceSerializer = NamespaceDetailSerializer


class ClusterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cluster
        fields = '__all__'

class TenantSerializer(serializers.ModelSerializer):
    active_ns_count = serializers.IntegerField(read_only=True, default=0)
    class Meta:
        model = Tenant
        fields = '__all__'

class TenantDetailSerializer(TenantSerializer):
    active_namespaces = serializers.SerializerMethodField()
    decommissioned_namespaces = serializers.SerializerMethodField()
    has_cso = serializers.SerializerMethodField()

    class Meta(TenantSerializer.Meta):
        fields = '__all__'

    # The tenant detail panel renders namespaces as a table, so it takes the list
    # payload. It previously used the full serializer while select_related'ing
    # only four of the nine relations that serializer touches, so every tenant
    # detail load fired a burst of per-namespace queries and shipped the raw YAML
    # of every custom resource.
    @extend_schema_field(OpenApiTypes.ANY)
    def get_active_namespaces(self, obj):
        qs = NamespaceListSerializer.optimize(obj.namespaces.filter(is_decommissioned=False))
        return NamespaceListSerializer(qs, many=True).data

    @extend_schema_field(OpenApiTypes.ANY)
    def get_decommissioned_namespaces(self, obj):
        qs = NamespaceListSerializer.optimize(obj.namespaces.filter(is_decommissioned=True))
        return NamespaceListSerializer(qs, many=True).data
        
    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_cso(self, obj):
        return obj.namespaces.filter(egress_router__isnull=False).exists()

class UserListSerializer(serializers.Serializer):
    email = serializers.CharField()
    # Namespaces and capsules are counted separately rather than summed into one
    # "projects" number: they are different kinds of access, and a total would
    # hide that someone's only access is to a capsule.
    access_count = serializers.IntegerField()
    capsule_count = serializers.IntegerField(required=False, default=0)


def _humanise(key):
    """`requestsEphemeralStorage` / `requests_storage` -> `Requests Ephemeral Storage`."""
    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', str(key).replace('_', ' '))
    return spaced.replace('-', ' ').strip().title()


def _leaf_fields(value, prefix=''):
    """Flatten a config block into label/value rows.

    Nested one level deep with a dotted label, because that is as far as the
    capsule chart actually nests and deeper would produce labels nobody can
    read. Anything below that is handed over as its own compact JSON string --
    still visible, still honest, and rare.
    """
    rows = []
    for key, item in value.items():
        label = f'{prefix}{_humanise(key)}'
        if isinstance(item, dict):
            if item and all(not isinstance(v, (dict, list)) for v in item.values()):
                rows.extend(_leaf_fields(item, prefix=f'{label} · '))
            else:
                rows.append({'name': key, 'label': label,
                             'value': json.dumps(item, separators=(', ', ': '))})
        elif isinstance(item, list):
            # A list of scalars reads as a list; a list of objects does not, so
            # it is summarised by count rather than printed as JSON soup.
            if all(not isinstance(v, (dict, list)) for v in item):
                rows.append({'name': key, 'label': label, 'value': item})
            else:
                rows.append({'name': key, 'label': label,
                             'value': f'{len(item)} entr{"y" if len(item) == 1 else "ies"}'})
        else:
            rows.append({'name': key, 'label': label, 'value': item})
    return rows


def _describe_block(key, value):
    """One config block as a DetailSection descriptor, or None if unrenderable."""
    if isinstance(value, dict):
        fields = _leaf_fields(value)
    elif isinstance(value, list):
        fields = [{'name': key, 'label': _humanise(key),
                   'value': value if all(not isinstance(v, (dict, list)) for v in value)
                   else f'{len(value)} entr{"y" if len(value) == 1 else "ies"}'}]
    else:
        fields = [{'name': key, 'label': _humanise(key), 'value': value}]
    return {'title': _humanise(key), 'fields': fields} if fields else None


class CapsuleSerializer(serializers.ModelSerializer):
    """A capsule and the quota it shares across its own namespaces.

    `quota` is nested rather than flattened because it is the point of a
    capsule: every value is stored exactly as the repo writes it ("16", "64Gi",
    "1000Mi"), since normalising them would lose the distinction between a
    request and a limit expressed in different units.
    """
    tenant = serializers.CharField(source='tenant.name', read_only=True)
    cluster = serializers.CharField(source='cluster.name', read_only=True)
    siglum = serializers.SerializerMethodField()
    quota = serializers.SerializerMethodField()
    harbor = serializers.SerializerMethodField()
    # The same three names the namespace list serializer uses, so the two
    # directories can render their feature chips from identical markup. A
    # capsule has no operators today; the field is present and empty so the
    # chip loop already works the day the chart grows managedServices.
    network_flows = serializers.SerializerMethodField()
    templates = serializers.SerializerMethodField()
    operators = serializers.SerializerMethodField()

    class Meta:
        model = Capsule
        fields = [
            'name', 'tenant', 'cluster', 'lifecycle', 'siglum', 'cost_center',
            'requester', 'request_ticket', 'is_decommissioned',
            'global_egress_ip_name', 'quota', 'harbor',
            'network_flows', 'templates', 'operators',
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_siglum(self, obj):
        return obj.effective_siglum

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_quota(self, obj):
        return {
            "enabled": obj.quota_enabled,
            "limitsCpu": obj.limits_cpu,
            "requestsCpu": obj.requests_cpu,
            "limitsMemory": obj.limits_memory,
            "requestsMemory": obj.requests_memory,
            "requestsEphemeralStorage": obj.requests_ephemeral_storage,
            "requestsStorage": obj.requests_storage,
        }

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_harbor(self, obj):
        return {"enable": obj.harbor_enabled, "storageQuota": obj.harbor_storage_quota_gb}

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_network_flows(self, obj):
        """Read out of the stored config rather than columns.

        A capsule's allowedFlows block is not promoted to model fields the way a
        namespace's is -- it lives in `config` verbatim. Shaped identically to
        the namespace serializer's so the templates match.
        """
        flows = (obj.config or {}).get('allowedFlows') or {}
        return {
            "enabled": bool(flows.get('enabled', flows.get('enable', False))),
            "dns": bool(flows.get('dnsResolutionEnabled', False)),
            "proxy": bool(flows.get('proxyEnabled', False)),
        }

    @extend_schema_field(OpenApiTypes.ANY)
    def get_templates(self, obj):
        # Names and kinds only; the list view reads nothing but the count.
        return [{"kind": c.kind, "name": c.name} for c in obj.custom_resources.all()]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_operators(self, obj):
        managed = (obj.config or {}).get('managedServices') or {}
        return {
            name: {"enabled": bool(conf.get('enabled', False))}
            for name, conf in managed.items() if isinstance(conf, dict)
        }


class CapsuleDetailSerializer(CapsuleSerializer):
    """Everything about one capsule, for the detail page.

    `config` is the rest of the provisioner block verbatim -- limit ranges,
    retention policy, network policy, allowed flows, robot accounts. The page
    renders it generically, so a key added to the capsule chart shows up without
    a dashboard change, which is the same bargain the namespace section registry
    makes.
    """
    owners = serializers.ListField(child=serializers.CharField(), read_only=True)
    users = serializers.ListField(child=serializers.CharField(), read_only=True)
    templates = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta(CapsuleSerializer.Meta):
        fields = CapsuleSerializer.Meta.fields + ['owners', 'users', 'templates', 'sections']

    @extend_schema_field(OpenApiTypes.ANY)
    def get_templates(self, obj):
        return [
            {"kind": c.kind, "name": c.name, "content": c.content}
            for c in obj.custom_resources.all()
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_sections(self, obj):
        """The remaining provisioner blocks, in the shape DetailSection renders.

        Previously this was handed over as raw `config` JSON and the page
        printed it into a <pre>. That is a config file on screen, not a UI, and
        it looked nothing like the namespace page beside it.

        The namespace equivalent is driven by an explicit registry
        (gitops/sections.py) because a namespace's blocks are known. A capsule's
        are not -- the chart is still growing keys, and the whole point of
        storing them verbatim is that a new one appears without a dashboard
        change. So the shape is derived rather than declared: each top-level
        block becomes a card, each leaf a labelled field. Same output contract,
        so the same component renders both.
        """
        return {key: _describe_block(key, value)
                for key, value in sorted((obj.config or {}).items())
                if _describe_block(key, value)}
