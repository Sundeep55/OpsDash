"""Generate a synthetic GitOps repo exercising every branch of the sync walk.

See tools/README.md. Usage: python tools/gitops_fixture.py <outdir>
"""
import os, shutil, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gitops_fixture"


FILES = {}

# ---------------------------------------------------------------- cluster-a
FILES["cluster-a/tenant-alpha/tenant-metadata.yaml"] = """
siglum: ABDEF
billing_code: CC-1001
requester: alice@example.com
tenant_request_ticket: REQ-0001
active_namespaces:
  - name: alpha-prod
    namespace_request_ticket: REQ-0002
    dcs.example.com/lifecycle: PROD
  - name: alpha-dev
    req_id: REQ-0003
    dcs.example.com/lifecycle: dev
    security_exception:
      request_ticket: SEC-0001
      granted_at: 2025-01-15
decommissioned_namespaces:
  - name: alpha-old
    request_ticket: REQ-0004
active_registry_mirrors:
  - namespace: alpha-prod
    name: legacy-mirror
    image: nginx
    url: https://legacy.example.com
"""

# full provisioner + siglum override (differs from tenant ABDEF) -> exercises 2.2
FILES["cluster-a/tenant-alpha/alpha-prod/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: prod
    siglum: ABXYZ
  additionalLabels:
    dcs.example.com/egressip_name: router-a
  devspaceConfig:
    isDevspace: false
  allowedFlows:
    enabled: true
    dnsResolutionEnabled: true
    proxyEnabled: false
    s3ConnectionEnabled: true
    connections:
      - from: web
        to: [db, cache]
        flows: [tcp/5432]
  routeException:
    enabled: true
    requestId: RE-1234
    grantedAt: 2025-03-01
  managedServices:
    postgresOperator:
      enabled: true
    lokiOperator:
      enabled: false
  resourceQuota:
    enabled: true
    requestsCpu: "4"
    limitsCpu: "8"
    requestsMemory: 16Gi
    limitsMemory: 32Gi
    requestsStorage: 100Gi
    requestsEphemeralStorage: 10Gi
  limitRange:
    storageMax: 50Gi
    storageMin: 1Gi
    containerCPU: "2"
    containerRequestCPU: 500m
    containerRAM: 4Gi
    containerRequestRAM: 512Mi
  harborOnboardingConfig:
    enable: true
    storageQuota: 50
    vulnerabilityScanning: true
    autoSbomGeneration: true
    cveAllowlist: [CVE-2024-1111]
  harborRobotAccounts:
    enabled: true
    robotAccounts:
      - nameSuffix: ci
        default: true
        permissions: [pull, push]
  project_owner_config:
    project_owner:
      initialUsers: [alice@example.com, BOB@example.com]
  project_user_config:
    project_users:
      initialUsers: [carol@example.com]
registry-config:
  registries:
    - name: upstream
      endpointUrl: https://registry.example.com
      providerName: harbor
  dockerRegistryReplications:
    - registry: upstream
      schedule: "0 2 * * *"
      filters:
        - name: library/**
        - tag: stable
"""

FILES["cluster-a/tenant-alpha/alpha-prod/Chart.yaml"] = """
apiVersion: v2
name: alpha-prod
version: 1.0.0
dependencies:
  - name: namespace-provisioner
    version: 2.3.1
"""

FILES["cluster-a/tenant-alpha/alpha-prod/templates/quota-crd.yaml"] = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: extra-config
data:
  key: value
---
apiVersion: v1
kind: Secret
metadata:
  name: extra-secret
stringData:
  token: abc
"""

# devspace namespace, no quota, no harbor -> exercises the delete branches
FILES["cluster-a/tenant-alpha/alpha-dev/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    env: dev
  devspaceConfig:
    isDevspace: true
    devspaceUser: dave@example.com
  allowedFlows:
    enable: false
  resourceQuota:
    enabled: false
  managedServices:
    certManagerOperator:
      enabled: true
"""
FILES["cluster-a/tenant-alpha/alpha-dev/Chart.yaml"] = """
apiVersion: v2
name: alpha-dev
version: 0.1.0
dependencies:
  - name: namespace-provisioner
    version: 2.3.1
"""

# decommissioned namespace under an active tenant
FILES["cluster-a/tenant-alpha/.decommissioned_namespaces/alpha-old_20240101/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: prod
"""

# ---------------------------------------------------------------- cluster-a: CSO / egress tenant
FILES["cluster-a/tenant-egress/tenant-metadata.yaml"] = """
siglum: ABCSO
wbs: CC-2002
requester: erin@example.com
"""
FILES["cluster-a/tenant-egress/egress-hub/values.yaml"] = """
egress:
  requiredLabels:
    dcs.example.com/lifecycle: prod
    siglum: ABCSO
  egressIPResources:
    - name: router-a
      egressIPs: [10.0.0.1, 10.0.0.2]
    - name: router-b
      egressIPs: [10.0.0.3]
"""
FILES["cluster-a/tenant-egress/egress-hub/Chart.yaml"] = """
apiVersion: v2
name: egress-hub
version: 1.0.0
dependencies:
  - name: egress-provisioner
    version: 0.9.0
"""

# excluded by name at the top of the walk
FILES["cluster-a/tenant-egress/egressip-pool.yaml"] = """
pool: [10.0.0.0/24]
"""

# ---------------------------------------------------------------- cluster-b: service mesh
FILES["cluster-b/tenant-beta/tenant-metadata.yaml"] = """
siglum: BCDEF
billing_code: CC-3003
requester: frank@example.com
active_namespaces:
  - name: beta-mesh-cp
    dcs.example.com/lifecycle: prod
  - name: beta-mesh-dp
    dcs.example.com/lifecycle: prod
"""
FILES["cluster-b/tenant-beta/beta-mesh-cp/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: prod
    siglum: BCDEF
  resourceQuota:
    enabled: true
    requestsCpu: 2000m
    limitsCpu: "4"
    requestsMemory: 8Gi
    limitsMemory: 16Gi
service-mesh:
  cluster:
    domain: mesh.example.com
  cp:
    tenant: tenant-beta
    kiali:
      name: kiali-beta
    gw:
      namespaces: [beta-gw]
  dataplane:
    namespaces:
      - name: beta-mesh-dp
"""
FILES["cluster-b/tenant-beta/beta-mesh-cp/Chart.yaml"] = """
apiVersion: v2
name: beta-mesh-cp
version: 1.2.0
dependencies:
  - name: namespace-provisioner
    version: 2.3.1
  - name: service-mesh
    version: 1.1.0
"""
FILES["cluster-b/tenant-beta/beta-mesh-dp/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: prod
"""

# GPU-requesting namespace: gpuConfig as it appears in the real repo, including
# the string-typed gpuCount and the nested limitRange.
FILES["cluster-b/tenant-beta/beta-gpu/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: prod
  resourceQuota:
    enabled: true
    requestsCpu: "8"
    limitsCpu: "16"
    requestsMemory: 32Gi
    limitsMemory: 64Gi
  gpuConfig:
    enabled: true
    type: "full"
    gpuCount: "3"
    limitRange:
      min: "0"
      max: "4"
      default: "0"
      defaultRequest: "0"
"""

# gpuConfig present but disabled -> must NOT create a row
FILES["cluster-a/tenant-alpha/alpha-nogpu/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: dev
  gpuConfig:
    enabled: false
    type: "shared"
    gpuCount: "0"
"""

# tenant with no metadata file at all -> siglum stays null
FILES["cluster-b/tenant-orphan/orphan-ns/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: staging
"""

# ---------------------------------------------------------------- decommissioned tenant
FILES["cluster-b/.decommissioned_tenants/tenant-gone/gone-ns/values.yaml"] = """
namespace-provisioner:
  requiredLabels:
    dcs.example.com/lifecycle: prod
"""
FILES["cluster-b/.decommissioned_tenants/tenant-gone/tenant-metadata.yaml"] = """
siglum: BCGONE
billing_code: CC-9999
"""

# malformed YAML -> must be caught per-file and not abort the run
FILES["cluster-a/tenant-alpha/alpha-prod/broken.yaml"] = """
namespace-provisioner:
  requiredLabels:
    lifecycle: [unclosed
"""


SIGLUM_ROOTS = ["ABDEF", "ABXYZ", "BCDEF", "CDEFG", "DEFGH", "EFGHI", "ABCSO", "BCGHI"]
OPERATORS = ["postgresOperator", "lokiOperator", "certManagerOperator",
             "kafkaOperator", "redisOperator", "elasticOperator"]


def add_scale(files, tenants, namespaces, clusters=("cluster-a", "cluster-b")):
    """Add bulk tenants/namespaces on top of the correctness fixture.

    Shapes the data like the real repo: most namespaces carry only a
    provisioner block and one chart dependency, a minority add operators,
    templates or mirrors. Used to measure behaviour at production scale --
    see tools/README.md.
    """
    per_tenant = max(1, round(namespaces / tenants))
    made_ns = 0

    for t in range(tenants):
        cluster = clusters[t % len(clusters)]
        tenant = f"gen-tenant-{t:04d}"
        siglum = SIGLUM_ROOTS[t % len(SIGLUM_ROOTS)]
        entries = []

        for n in range(per_tenant):
            if made_ns >= namespaces:
                break
            ns = f"gen-ns-{made_ns:04d}"
            made_ns += 1
            lifecycle = "prod" if n % 3 == 0 else "dev"
            entries.append(f"  - name: {ns}\n    lifecycle: {lifecycle}\n")

            ops = ""
            if made_ns % 3 == 0:
                chosen = OPERATORS[: (made_ns % len(OPERATORS)) + 1]
                ops = "  managedServices:\n" + "".join(
                    f"    {o}:\n      enabled: {'true' if i % 2 == 0 else 'false'}\n"
                    for i, o in enumerate(chosen))

            files[f"{cluster}/{tenant}/{ns}/values.yaml"] = f"""
namespace-provisioner:
  requiredLabels:
    lifecycle: {lifecycle}
    siglum: {siglum}
  resourceQuota:
    enabled: true
    requestsCpu: "{2 + (n % 8)}"
    limitsCpu: "{4 + (n % 16)}"
    requestsMemory: {8 + (n % 32)}Gi
    limitsMemory: {16 + (n % 64)}Gi
    requestsStorage: {50 + (n % 200)}Gi
{ops}  harborOnboardingConfig:
    enable: {'true' if made_ns % 2 == 0 else 'false'}
    storageQuota: {10 + (n % 90)}
  project_owner_config:
    project_owner:
      initialUsers: [owner{made_ns % 120}@example.com]
  project_user_config:
    project_users:
      initialUsers: [user{made_ns % 400}@example.com, user{(made_ns + 7) % 400}@example.com]
"""
            files[f"{cluster}/{tenant}/{ns}/Chart.yaml"] = f"""
apiVersion: v2
name: {ns}
version: 1.0.{n}
dependencies:
  - name: namespace-provisioner
    version: 2.3.{made_ns % 5}
"""
            if made_ns % 12 == 0:
                files[f"{cluster}/{tenant}/{ns}/templates/extra.yaml"] = f"""
apiVersion: v1
kind: ConfigMap
metadata:
  name: cfg-{ns}
data:
  payload: "{'x' * 400}"
"""

        files[f"{cluster}/{tenant}/tenant-metadata.yaml"] = (
            f"siglum: {siglum}\nbilling_code: CC-{4000 + t}\n"
            f"requester: req{t % 50}@example.com\nactive_namespaces:\n" + "".join(entries)
        )
    return made_ns


def main():
    scale = None
    if "--scale" in sys.argv:
        i = sys.argv.index("--scale")
        tenants, namespaces = (int(x) for x in sys.argv[i + 1].split(","))
        scale = (tenants, namespaces)

    if os.path.exists(ROOT):
        shutil.rmtree(ROOT)

    if scale:
        made = add_scale(FILES, *scale)
        print(f"scale: +{scale[0]} tenants, +{made} namespaces")

    for rel, body in FILES.items():
        path = os.path.join(ROOT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body.lstrip())
    print(f"wrote {len(FILES)} files to {ROOT}")


if __name__ == "__main__":
    main()
