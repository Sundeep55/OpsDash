"""Dashboard aggregates: KPIs, lifecycle counts and the siglum org tree."""
import collections

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from dashboard.api.filters import parse_cpu, parse_mem_gi
from dashboard.models import Namespace, Tenant


class GlobalAnalyticsView(APIView):
    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        cluster = request.query_params.get('cluster')
        active_namespaces = Namespace.objects.filter(is_decommissioned=False).select_related('tenant', 'cluster', 'resource_quota').prefetch_related('operators', 'helm_deployments')
        active_tenants = Tenant.objects.filter(is_decommissioned=False)
        
        if cluster and cluster != 'All':
            active_namespaces = active_namespaces.filter(cluster__name=cluster)
            active_tenants = active_tenants.filter(cluster__name=cluster)

        def get_default_cluster_resources():
            return {
                "cpu_req": 0, "cpu_limit": 0, "mem_req": 0, "mem_limit": 0,
                "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0, "total": 0},
                "operators": collections.defaultdict(int),
                "charts": collections.defaultdict(int),
                "siglum_tree": {}
            }

        analytics = {
            "global_kpis": {
                "tenants": active_tenants.count(),
                "namespaces": active_namespaces.count(),
                "cpu_req": 0,
                "mem_req": 0
            },
            "lifecycles": {"dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0},
            "operators": collections.defaultdict(int),
            "chart_usage": collections.defaultdict(int),
            "cluster_resources": collections.defaultdict(get_default_cluster_resources),
            "siglum_tree": {}
        }

        for ns in active_namespaces:
            c_name = ns.cluster.name
            cr = analytics["cluster_resources"][c_name]
            
            cr["lifecycles"]["total"] += 1
            
            if getattr(ns, 'is_cso', False): 
                analytics["lifecycles"]["egress"] += 1
                cr["lifecycles"]["egress"] += 1
            elif ns.is_devspace: 
                analytics["lifecycles"]["devspace"] += 1
                cr["lifecycles"]["devspace"] += 1
            elif ns.lifecycle and ns.lifecycle.lower() == 'prod': 
                analytics["lifecycles"]["prod"] += 1
                cr["lifecycles"]["prod"] += 1
            elif ns.lifecycle and ns.lifecycle.lower() == 'dev': 
                analytics["lifecycles"]["dev"] += 1
                cr["lifecycles"]["dev"] += 1
            else:
                analytics["lifecycles"]["unassigned"] += 1
                cr["lifecycles"]["unassigned"] += 1

            if hasattr(ns, 'resource_quota') and ns.resource_quota:
                rq = ns.resource_quota
                cpu_r = parse_cpu(rq.requests_cpu)
                cpu_l = parse_cpu(rq.limits_cpu)
                mem_r = parse_mem_gi(rq.requests_memory)
                mem_l = parse_mem_gi(rq.limits_memory)

                analytics["global_kpis"]["cpu_req"] += cpu_r
                analytics["global_kpis"]["mem_req"] += mem_r

                cr["cpu_req"] += cpu_r
                cr["cpu_limit"] += cpu_l
                cr["mem_req"] += mem_r
                cr["mem_limit"] += mem_l

            for op in ns.operators.all():
                if op.is_enabled:
                    analytics["operators"][op.name] += 1
                    cr["operators"][op.name] += 1

            for chart in ns.helm_deployments.all():
                key = f"{chart.chart_name} (v{chart.version})"
                analytics["chart_usage"][key] += 1
                cr["charts"][key] += 1

            siglum = ns.effective_siglum
            if siglum and siglum != "N/A":
                s_str = siglum.upper().strip()
                start_idx = 2 if len(s_str) >= 2 else 1
                
                current_level = analytics["siglum_tree"]
                for i in range(start_idx, len(s_str) + 1):
                    prefix = s_str[:i]
                    if prefix not in current_level:
                        current_level[prefix] = {"stats": {"tenants": set(), "ns_count": 0, "dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0}, "children": {}}
                    node = current_level[prefix]["stats"]
                    node["tenants"].add(ns.tenant.name)
                    node["ns_count"] += 1
                    
                    if getattr(ns, 'is_cso', False): node["egress"] += 1
                    elif ns.is_devspace: node["devspace"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'prod': node["prod"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'dev': node["dev"] += 1
                    else: node["unassigned"] += 1
                        
                    current_level = current_level[prefix]["children"]
                    
                c_level = cr["siglum_tree"]
                for i in range(start_idx, len(s_str) + 1):
                    prefix = s_str[:i]
                    if prefix not in c_level:
                        c_level[prefix] = {"stats": {"tenants": set(), "ns_count": 0, "dev": 0, "prod": 0, "devspace": 0, "egress": 0, "unassigned": 0}, "children": {}}
                    c_node = c_level[prefix]["stats"]
                    c_node["tenants"].add(ns.tenant.name)
                    c_node["ns_count"] += 1
                    
                    if getattr(ns, 'is_cso', False): c_node["egress"] += 1
                    elif ns.is_devspace: c_node["devspace"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'prod': c_node["prod"] += 1
                    elif ns.lifecycle and ns.lifecycle.lower() == 'dev': c_node["dev"] += 1
                    else: c_node["unassigned"] += 1
                        
                    c_level = c_level[prefix]["children"]

        analytics["operators"] = dict(sorted(analytics["operators"].items(), key=lambda item: item[1], reverse=True))
        analytics["chart_usage"] = dict(sorted(analytics["chart_usage"].items(), key=lambda item: (-item[1], item[0].lower())))
        
        def serialize_tree(tree_level):
            for prefix, node in tree_level.items():
                node["stats"]["tenants"] = len(node["stats"]["tenants"])
                serialize_tree(node["children"])
                
        serialize_tree(analytics["siglum_tree"])
        
        for c_name, cr_data in analytics["cluster_resources"].items():
            cr_data["operators"] = dict(sorted(cr_data["operators"].items(), key=lambda item: item[1], reverse=True))
            cr_data["charts"] = dict(sorted(cr_data["charts"].items(), key=lambda item: (-item[1], item[0].lower())))
            serialize_tree(cr_data["siglum_tree"])

        return Response(analytics)
