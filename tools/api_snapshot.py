"""Dump every DB table and every API response to a directory, for before/after diffing.

See tools/README.md. Usage: PYTHONPATH=. python tools/api_snapshot.py <outdir>
"""
import os, sys, json, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ops_portal.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "snapshot-key")
django.setup()

from django.apps import apps
from django.test import Client
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ DB dump
tables = {}
for model in apps.get_app_config("dashboard").get_models():
    rows = list(model.objects.all().values())
    # sort deterministically on the full row repr so ordering never causes false diffs
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True, cls=DjangoJSONEncoder))
    tables[model.__name__] = rows

with open(os.path.join(OUT, "_db.json"), "w") as fh:
    json.dump(tables, fh, indent=2, sort_keys=True, cls=DjangoJSONEncoder)

# ------------------------------------------------------------------ API dump
User = get_user_model()
user, _ = User.objects.get_or_create(username="snapshot", defaults={"is_staff": True, "is_superuser": True})
client = Client()
client.force_login(user)

ENDPOINTS = [
    "/api/v2/clusters/",
    "/api/v2/tenants/",
    "/api/v2/tenants/tenant-alpha/",
    "/api/v2/tenants/tenant-beta/",
    "/api/v2/namespaces/",
    "/api/v2/namespaces/?page_size=500&is_decommissioned=false",
    "/api/v2/namespaces/alpha-prod/",
    "/api/v2/namespaces/egress-hub/",
    "/api/v2/namespaces/beta-mesh-cp/",
    "/api/v2/namespaces/?has_flows=true",
    "/api/v2/namespaces/?has_route_exception=true",
    "/api/v2/namespaces/?has_cve_exception=true",
    "/api/v2/namespaces/?has_mirror=true",
    "/api/v2/namespaces/?has_templates=true",
    "/api/v2/namespaces/?is_cso=true",
    "/api/v2/namespaces/?lifecycle=prod&is_devspace=false",
    "/api/v2/namespaces/?lifecycle=unassigned",
    "/api/v2/namespaces/?operator=postgresOperator",
    "/api/v2/namespaces/?chart=namespace-provisioner%20(v2.3.1)",
    "/api/v2/users/",
    "/api/v2/users/alice@example.com/",
    "/api/v2/siglums/",
    "/api/v2/siglums/?search=AB",
    "/api/v2/requests/",
    "/api/v2/analytics/",
    "/api/v2/analytics/?cluster=cluster-a",
    "/api/v2/platform/clusters/",
    "/api/v2/platform/gpu-allocations/",
    "/api/v2/finops/quotas/",
    "/api/v2/finops/unattributed-spend/",
    "/api/v2/devex/devspaces/",
    "/api/v2/devex/project-rosters/",
    "/api/v2/security/route-exceptions/",
    "/api/v2/security/robot-accounts/",
    "/api/v2/security/namespace-posture/",
    "/api/v2/sync/status/",
    "/api/v2/stack/helm-deployments/",
    "/api/v2/stack/upstream-mirrors/",
    "/api/v2/network/egress-routing/",
    "/api/v2/network/service-mesh/",
    "/api/sync/status/",
]

api = {}
for ep in ENDPOINTS:
    try:
        resp = client.get(ep)
        try:
            body = json.loads(resp.content)
        except Exception:
            body = resp.content.decode("utf-8", "replace")[:500]
        api[ep] = {"status": resp.status_code, "body": body}
    except Exception as exc:
        api[ep] = {"status": "EXCEPTION", "body": f"{type(exc).__name__}: {exc}"}

with open(os.path.join(OUT, "_api.json"), "w") as fh:
    json.dump(api, fh, indent=2, sort_keys=True, cls=DjangoJSONEncoder)

print(f"snapshot -> {OUT}")
print(f"  tables: {sum(len(v) for v in tables.values())} rows across {len(tables)} models")
bad = {k: v['status'] for k, v in api.items() if v['status'] not in (200,)}
print(f"  api: {len(api)} endpoints, non-200: {bad if bad else 'none'}")
