"""Sync a fixture, mutate it the way Git would, re-sync, and assert the DB followed.

Covers the reconciliation bugs a single sync cannot reveal: records that are
only ever created or set, never updated or removed. See tools/README.md.

Usage: PYTHONPATH=. python tools/mutation_check.py <fixture> <mutated-copy>
"""
import os, shutil, subprocess, sys, django

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SRC, DST = sys.argv[1], sys.argv[2]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ops_portal.settings")
django.setup()
from dashboard.models import Namespace, Operator, ServiceMeshControlPlane, Tenant  # noqa: E402


def sync(path):
    subprocess.run([PY, "manage.py", "sync_gitops", "--repo-path", path],
                   cwd=REPO, capture_output=True, check=True)


def mutate():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)

    # 1. remove postgresOperator from alpha-prod's managedServices
    p = f"{DST}/cluster-a/tenant-alpha/alpha-prod/values.yaml"
    s = open(p).read().replace(
        "  managedServices:\n    postgresOperator:\n      enabled: true\n    lokiOperator:\n      enabled: false\n",
        "  managedServices:\n    lokiOperator:\n      enabled: false\n")
    open(p, "w").write(s)

    # 2. recommission tenant-gone: move it out of .decommissioned_tenants/
    os.makedirs(f"{DST}/cluster-b/tenant-gone", exist_ok=True)
    for f in os.listdir(f"{DST}/cluster-b/.decommissioned_tenants/tenant-gone"):
        shutil.move(f"{DST}/cluster-b/.decommissioned_tenants/tenant-gone/{f}",
                    f"{DST}/cluster-b/tenant-gone/{f}")
    shutil.rmtree(f"{DST}/cluster-b/.decommissioned_tenants")

    # 3. move orphan-ns from tenant-orphan to tenant-beta
    os.makedirs(f"{DST}/cluster-b/tenant-beta/orphan-ns", exist_ok=True)
    shutil.move(f"{DST}/cluster-b/tenant-orphan/orphan-ns/values.yaml",
                f"{DST}/cluster-b/tenant-beta/orphan-ns/values.yaml")
    shutil.rmtree(f"{DST}/cluster-b/tenant-orphan")

    # 4. alpha-dev stops being a devspace
    p = f"{DST}/cluster-a/tenant-alpha/alpha-dev/values.yaml"
    s = open(p).read().replace(
        "  devspaceConfig:\n    isDevspace: true\n    devspaceUser: dave@example.com\n", "")
    open(p, "w").write(s)

    # 5. beta-mesh-dp is removed from the mesh dataplane
    p = f"{DST}/cluster-b/tenant-beta/beta-mesh-cp/values.yaml"
    s = open(p).read().replace("    namespaces:\n      - name: beta-mesh-dp\n",
                               "    namespaces: []\n")
    open(p, "w").write(s)


def check(label, actual, expected):
    ok = actual == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(f"          got {actual!r}, expected {expected!r}")
    return ok


sync(SRC)
print("baseline synced\n")
mutate()
sync(DST)
print("mutated repo synced. Assertions:\n")

results = []
ops = sorted(Operator.objects.filter(namespace_id='alpha-prod').values_list('name', flat=True))
results.append(check("operator removed from Git is pruned", ops, ['lokiOperator']))

t = Tenant.objects.filter(name='tenant-gone').first()
results.append(check("recommissioned tenant clears is_decommissioned",
                     t.is_decommissioned if t else 'ROW GONE', False))

n = Namespace.objects.filter(name='orphan-ns').first()
results.append(check("moved namespace survives and follows its new tenant",
                     n.tenant_id if n else 'ROW DELETED', 'tenant-beta'))

d = Namespace.objects.filter(name='alpha-dev').first()
results.append(check("namespace that stopped being a devspace resets",
                     (d.is_devspace, d.devspace_user), (False, None)))

m = Namespace.objects.filter(name='beta-mesh-dp').first()
results.append(check("namespace dropped from mesh dataplane is detached",
                     m.service_mesh_cp_id, None))

results.append(check("mesh control plane itself still exists",
                     ServiceMeshControlPlane.objects.filter(namespace_id='beta-mesh-cp').exists(), True))

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
