#!/usr/bin/env python3
"""Generate a large, realistic GitOps tree for browsing the dashboard locally.

Different job from tools/gitops_fixture.py. That one is deliberately tiny and
hand-written so every branch of the sync walk is visible and assertable; this
one is deliberately big and generated, so the UI can be exercised at something
like real scale -- pagination, the siglum drill-down, the expiry banner, cluster
scoping, empty states.

Nothing here talks to GitLab. Point the sync at the output directory:

    python3 tools/demo_estate.py /tmp/demo-estate
    python manage.py sync_gitops --repo-path /tmp/demo-estate

The sync falls back to a local path whenever GITLAB_URL / GITLAB_TOKEN /
GITLAB_PROJECT_ID are not all set, so an ordinary development shell already
takes this path -- see dashboard/gitops/fetcher.py.

Deterministic: the seed is fixed, so the same command always produces the same
estate and a screenshot taken today still matches tomorrow. Pass --seed to get a
different one.

    --tenants N     how many active tenants per cluster (default 100)
    --seed N        change the shape of the estate
    --domain X      the label domain, default dcs.example.com

Scale note: the defaults produce roughly the size described for production --
2 clusters, ~200 tenants, ~800 namespaces -- which is the point. A dashboard
that looks fine with three rows is not evidence of anything.
"""
import argparse
import os
import random
import shutil
from datetime import date, timedelta

# --------------------------------------------------------------- vocabulary
# Real-ish names, because "tenant-001" makes every list look the same and hides
# the truncation and sorting problems that real names cause.
BUSINESS = [
    'atlas', 'beacon', 'cedar', 'delta', 'ember', 'fathom', 'granite', 'harbor',
    'indigo', 'juniper', 'kestrel', 'lantern', 'meridian', 'nimbus', 'onyx',
    'pinnacle', 'quarry', 'ridge', 'summit', 'tundra', 'umbra', 'vertex',
    'willow', 'xenon', 'yarrow', 'zephyr', 'anvil', 'borealis', 'cobalt',
    'dynamo', 'estuary', 'flint', 'gossamer', 'hollow', 'ironwood', 'jetty',
]
SUFFIX = ['analytics', 'billing', 'core', 'data', 'events', 'gateway', 'ident',
          'ledger', 'mesh', 'portal', 'registry', 'search', 'telemetry', 'vault']

# Two divisions, then departments beneath them, so the siglum drill-down has
# something to drill through: the tree records every prefix from 2 characters up.
DIVISIONS = ['AB', 'BC', 'CD']
DEPARTMENTS = ['DEF', 'GHI', 'JKL', 'MNO', 'PQR']

OPERATORS = [
    'argocdOperator', 'gitlabOperator', 'cloudnativepgOperator',
    'certManagerOperator', 'lokiOperator', 'perconaMongodbOperator',
    'keycloakOperator', 'strimziOperator', 'postgresOperator',
]

FIRST = ['alice', 'bob', 'carol', 'dave', 'erin', 'frank', 'grace', 'heidi',
         'ivan', 'judy', 'mallory', 'niaj', 'olivia', 'peggy', 'rupert', 'sybil']
LAST = ['adams', 'baker', 'chen', 'diaz', 'evans', 'foster', 'gupta', 'hansen',
        'ito', 'kowalski', 'lopez', 'mehta', 'novak', 'okafor', 'pereira', 'singh']


class Estate:
    def __init__(self, root, tenants_per_cluster, seed, domain):
        self.root = root
        self.per_cluster = tenants_per_cluster
        self.domain = domain
        self.rng = random.Random(seed)
        self.files = {}
        self.stats = {
            'tenants': 0, 'namespaces': 0, 'capsules': 0, 'devspaces': 0,
            'cso': 0, 'mesh': 0, 'mirrors': 0, 'route_exceptions': 0,
            'route_exceptions_values': 0,
            'expired': 0, 'expiring': 0, 'decommissioned_ns': 0,
            'decommissioned_tenants': 0,
        }

    # ----------------------------------------------------------- helpers
    def write(self, path, body):
        self.files[path] = body.lstrip('\n')

    def person(self):
        return f'{self.rng.choice(FIRST)}.{self.rng.choice(LAST)}@example.com'

    def ticket(self, prefix='REQ'):
        return f'{prefix}-{self.rng.randint(10000, 99999)}'

    def siglum(self):
        return self.rng.choice(DIVISIONS) + self.rng.choice(DEPARTMENTS)

    def cost_center(self):
        return f'CC-{self.rng.randint(1000, 9999)}'

    def quota(self, scale=1):
        cpu = self.rng.choice([2, 4, 8, 16, 32]) * scale
        mem = cpu * self.rng.choice([2, 4])
        return f"""
    enabled: true
    requestsCpu: "{cpu}"
    limitsCpu: "{cpu * 2}"
    requestsMemory: {mem}Gi
    limitsMemory: {mem * 2}Gi
    requestsStorage: {self.rng.choice([50, 100, 200, 500])}Gi
    requestsEphemeralStorage: {self.rng.choice([5, 10, 20])}Gi"""

    def operators_block(self, count):
        chosen = self.rng.sample(OPERATORS, count)
        lines = []
        for name in chosen:
            # A disabled operator is still a record; the prune and the analytics
            # counts both have to cope with it.
            enabled = 'true' if self.rng.random() > 0.25 else 'false'
            lines.append(f'    {name}:\n      enabled: {enabled}')
        return '\n'.join(lines)

    # ------------------------------------------------------------ builders
    def build(self):
        for cluster in ('cluster-a', 'cluster-b'):
            self.build_cluster(cluster)
        # Ignored by name wherever it appears -- present so the skip is exercised.
        self.write('cluster-a/egressip-pool.yaml', 'pool: [10.20.0.0/16]\n')
        return self.files

    def build_cluster(self, cluster):
        names = self.rng.sample(BUSINESS, min(self.per_cluster, len(BUSINESS)))
        # More tenants than distinct words: suffix them, the way real estates do.
        pool = []
        i = 0
        while len(pool) < self.per_cluster:
            base = names[i % len(names)]
            round_no = i // len(names)
            pool.append(base if round_no == 0 else f'{base}-{SUFFIX[round_no % len(SUFFIX)]}')
            i += 1

        # Tenant names are scoped per cluster, but namespace names are global --
        # the sync says so out loud when two clusters claim one name. Giving each
        # cluster its own tenant vocabulary keeps the generated estate valid
        # instead of exercising a warning path on every run.
        for tenant in pool:
            self.build_tenant(cluster, f'{tenant}-{cluster[-1]}')

        # One egress/CSO tenant per cluster, providing the routers the ordinary
        # namespaces reference.
        self.build_egress_tenant(cluster)
        # A wholly decommissioned tenant, so that filter has something to find.
        self.build_decommissioned_tenant(cluster)

    def build_tenant(self, cluster, tenant):
        rng = self.rng
        siglum = self.siglum()
        base = f'{cluster}/{tenant}'
        self.stats['tenants'] += 1

        # Long-tailed on purpose: most tenants are small, a few are large. A flat
        # distribution makes every tenant page look the same and hides how the
        # roster behaves when it is long.
        ns_count = rng.choices([1, 2, 3, 4, 5, 8, 14], weights=[16, 24, 22, 16, 12, 7, 3])[0]
        namespaces, meta_entries, decommissioned = [], [], []

        for n in range(ns_count):
            kind = rng.choices(
                ['standard', 'devspace', 'mesh'],
                weights=[78, 15, 7],
            )[0]
            name = self.namespace_name(tenant, n, kind)
            lifecycle = rng.choices(['prod', 'dev', None], weights=[45, 50, 5])[0]
            namespaces.append((name, kind, lifecycle))

            entry = [f'  - name: {name}', f'    namespace_request_ticket: {self.ticket()}']
            if lifecycle:
                entry.append(f'    {self.domain}/lifecycle: {lifecycle}')

            # Route exceptions are dev-only and time-limited. Spread the grant
            # dates so the estate contains active, expiring and already-expired
            # waivers -- otherwise the banner has nothing to show and the whole
            # feature looks like it works when it has simply never fired.
            if lifecycle == 'dev' and rng.random() < 0.18:
                age = rng.choice([5, 20, 45, 70, 85, 95, 120, 200])
                granted = date.today() - timedelta(days=age)
                entry.append('    security_exception:')
                entry.append(f'      request_ticket: {self.ticket("SEC")}')
                entry.append(f'      granted_at: {granted.isoformat()}')
                self.stats['route_exceptions'] += 1
                remaining = 90 - age
                if remaining < 0:
                    self.stats['expired'] += 1
                elif remaining <= 30:
                    self.stats['expiring'] += 1
            meta_entries.append('\n'.join(entry))

            self.build_namespace(base, name, kind, lifecycle, siglum, tenant, cluster)

        if rng.random() < 0.20:
            dead = f'{tenant}-legacy'
            decommissioned.append(f'  - name: {dead}\n    request_ticket: {self.ticket()}')
            self.write(
                f'{base}/.decommissioned_namespaces/{dead}_20240301/values.yaml',
                f"""
namespace-provisioner:
  requiredLabels:
    {self.domain}/lifecycle: prod
    siglum: {siglum}
""")
            self.stats['decommissioned_ns'] += 1

        # A capsule: a delegated slice whose own namespaces the estate does not
        # track. Deliberately common enough here to fill a directory, because
        # the capsule tab and the dashboard split are new and need real rows.
        if rng.random() < 0.28:
            self.build_capsule(base, tenant, siglum, cluster)

        mirrors = ''
        if rng.random() < 0.25 and namespaces:
            target = namespaces[0][0]
            mirrors = f"""
active_registry_mirrors:
  - namespace: {target}
    name: upstream-cache
    image: library/nginx
    url: https://registry.example.com
"""

        self.write(f'{base}/tenant-metadata.yaml', f"""
siglum: {siglum}
billing_code: {self.cost_center()}
requester: {self.person()}
tenant_request_ticket: {self.ticket()}
active_namespaces:
{chr(10).join(meta_entries)}
{('decommissioned_namespaces:' + chr(10) + chr(10).join(decommissioned)) if decommissioned else ''}
{mirrors}
""")

    def namespace_name(self, tenant, index, kind):
        """Unique within the tenant, and the tenant is unique within the estate.

        The suffix is indexed rather than random: drawing it randomly picked the
        same word twice for one tenant often enough that the generator claimed
        more namespaces than the sync ingested, and the two silently disagreed.
        """
        if kind == 'devspace':
            return f'dcsc-ds-{tenant}-{index}'
        if kind == 'mesh':
            return f'dcsc-{tenant}-service-mesh'
        return f'dcsc-{tenant}-{SUFFIX[index % len(SUFFIX)]}'

    def build_namespace(self, base, name, kind, lifecycle, siglum, tenant, cluster):
        rng = self.rng
        self.stats['namespaces'] += 1
        path = f'{base}/{name}'
        labels = [f'    siglum: {siglum}']
        if lifecycle:
            labels.insert(0, f'    {self.domain}/lifecycle: {lifecycle}')

        extra_labels = []
        if rng.random() < 0.3:
            extra_labels.append(f'    {self.domain}/egressip_name: router-{cluster[-1]}-{rng.randint(1, 3)}')
        extra_labels.append(f'    {self.domain}/cost_center: {self.cost_center()}')

        if kind == 'devspace':
            self.stats['devspaces'] += 1
            devspace = f"""
  devspaceConfig:
    isDevspace: true
    devspaceUser: {self.person()}"""
        else:
            devspace = """
  devspaceConfig:
    isDevspace: false"""

        flows = ''
        if rng.random() < 0.45:
            flows = f"""
  allowedFlows:
    enabled: true
    dnsResolutionEnabled: {'true' if rng.random() < 0.7 else 'false'}
    proxyEnabled: {'true' if rng.random() < 0.4 else 'false'}
    s3ConnectionEnabled: {'true' if rng.random() < 0.3 else 'false'}
    connections:
      - from: web
        to: [db, cache]
        flows: [tcp/5432, tcp/6379]"""

        route_exception = ''
        # Mirrors the tenant-metadata grant. The metadata file is the audit
        # record and wins where the two disagree, but the pipeline writes both,
        # so both are present here.
        if lifecycle == 'dev' and rng.random() < 0.18:
            self.stats['route_exceptions_values'] += 1
            route_exception = f"""
  routeException:
    enabled: true
    requestId: {self.ticket('RE')}
    grantedAt: {(date.today() - timedelta(days=rng.choice([10, 40, 80, 100]))).isoformat()}"""

        harbor = ''
        if rng.random() < 0.6:
            harbor = f"""
  harborOnboardingConfig:
    enable: true
    storageQuota: {rng.choice([20, 50, 100, 200])}
    vulnerabilityScanning: true
    autoSbomGeneration: {'true' if rng.random() < 0.5 else 'false'}
  harborRobotAccounts:
    enabled: true
    robotAccounts:
      - nameSuffix: ci
        default: true
        permissions: [pull, push]
      - nameSuffix: readonly
        default: false
        permissions: [pull]"""

        owners = [self.person() for _ in range(rng.randint(1, 2))]
        users = [self.person() for _ in range(rng.randint(0, 3))]

        self.write(f'{path}/values.yaml', f"""
namespace-provisioner:
  requiredLabels:
{chr(10).join(labels)}
  additionalLabels:
{chr(10).join(extra_labels)}{devspace}{flows}{route_exception}
  managedServices:
{self.operators_block(rng.randint(1, 4))}
  resourceQuota:{self.quota()}
  limitRange:
    storageMax: 50Gi
    storageMin: 1Gi
    containerCPU: "2"
    containerRequestCPU: 500m
    containerRAM: 4Gi
    containerRequestRAM: 512Mi{harbor}
  project_owner_config:
    project_owner:
      initialUsers: [{', '.join(owners)}]
  project_user_config:
    project_users:
      initialUsers: [{', '.join(users) if users else ''}]
""" + self.mesh_block(kind, name, tenant, base))

        self.write(f'{path}/Chart.yaml', f"""
apiVersion: v2
name: {name}
version: {rng.choice(['1.0.0', '1.2.3', '2.0.1', '2.3.1'])}
dependencies:
  - name: namespace-provisioner
    version: {rng.choice(['2.3.1', '2.4.0', '3.0.0'])}
""")

        if rng.random() < 0.18:
            self.write(f'{path}/templates/extra.yaml', f"""
apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}-config
data:
  tuning: "on"
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {name}-reaper
spec:
  schedule: "0 3 * * *"
""")

        if rng.random() < 0.12:
            self.stats['mirrors'] += 1
            self.write(f'{path}/values.yaml', self.files[f'{path}/values.yaml'] + f"""
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
""")

    def mesh_block(self, kind, name, tenant, base):
        if kind != 'mesh':
            return ''
        self.stats['mesh'] += 1
        return f"""
service-mesh:
  cluster:
    domain: {tenant}.mesh.example.com
  dataplane:
    namespaces:
      - name: dcsc-{tenant}-core
      - name: None
"""

    def build_capsule(self, base, tenant, siglum, cluster):
        rng = self.rng
        self.stats['capsules'] += 1
        name = f'dcsc-{tenant}-capsule'
        lifecycle = rng.choices(['prod', 'dev', None], weights=[35, 60, 5])[0]
        labels = [f'    siglum: {siglum}']
        if lifecycle:
            labels.insert(0, f'    {self.domain}/lifecycle: {lifecycle}')

        self.write(f'{base}/{name}/values.yaml', f"""
tenant-provisioner:
  requiredLabels:
{chr(10).join(labels)}
  additionalLabels:
    {self.domain}/cost_center: {self.cost_center()}
  additionalAnnotations:
    tenant_owner: {self.person()}
  globalEgressIpName: router-{cluster[-1]}-{rng.randint(1, 3)}
  resourceQuota:{self.quota(scale=2)}
  harborOnboardingConfig:
    enable: true
    storageQuota: {rng.choice([100, 200, 500])}
  limitRange:
    containerCPU: "4"
    containerRAM: 8Gi
  networkPolicy:
    enabled: true
  allowedFlows:
    enabled: {'true' if rng.random() < 0.5 else 'false'}
    dnsResolutionEnabled: true
  project_owner_config:
    project_owner:
      initialUsers: [{self.person()}, {self.person()}]
  project_user_config:
    project_users:
      initialUsers: [{self.person()}]
""")
        self.write(f'{base}/{name}/Chart.yaml', f"""
apiVersion: v2
name: {name}
version: 1.0.0
dependencies:
  - name: dcs-tenant-provisioner
    version: 1.4.0
""")
        if rng.random() < 0.3:
            self.write(f'{base}/{name}/templates/policy.yaml', f"""
apiVersion: v1
kind: ResourceQuota
metadata:
  name: {name}-shared
spec:
  hard:
    pods: "200"
""")

    def build_egress_tenant(self, cluster):
        letter = cluster[-1]
        base = f'{cluster}/tenant-egress-{letter}'
        siglum = DIVISIONS[0] + 'CSO'
        self.stats['tenants'] += 1
        self.stats['namespaces'] += 1
        self.stats['cso'] += 1
        routers = []
        for i in range(1, 4):
            ips = [f'10.{ord(letter) - 96}.{i}.{n}' for n in range(1, self.rng.randint(2, 5))]
            routers.append(f'    - name: router-{letter}-{i}\n      egressIPs: [{", ".join(ips)}]')

        self.write(f'{base}/tenant-metadata.yaml', f"""
siglum: {siglum}
wbs: {self.cost_center()}
requester: {self.person()}
tenant_request_ticket: {self.ticket()}
""")
        self.write(f'{base}/dcsc-cso-egress-hub-{letter}/values.yaml', f"""
egress:
  requiredLabels:
    {self.domain}/lifecycle: prod
    siglum: {siglum}
  egressIPResources:
{chr(10).join(routers)}
""")
        self.write(f'{base}/dcsc-cso-egress-hub-{letter}/Chart.yaml', """
apiVersion: v2
name: egress-hub
version: 1.0.0
dependencies:
  - name: egress-provisioner
    version: 0.9.0
""")
        self.write(f'{base}/egressip-pool.yaml', 'pool: [10.0.0.0/16]\n')

    def build_decommissioned_tenant(self, cluster):
        self.stats['decommissioned_tenants'] += 1
        name = f'retired-division-{cluster[-1]}'
        base = f'{cluster}/.decommissioned_tenants/{name}_20240115'
        self.write(f'{base}/tenant-metadata.yaml', f"""
siglum: {DIVISIONS[-1]}ZZZ
requester: {self.person()}
tenant_request_ticket: {self.ticket()}
""")
        self.write(f'{base}/dcsc-{name}-core/values.yaml', f"""
namespace-provisioner:
  requiredLabels:
    {self.domain}/lifecycle: prod
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('outdir', nargs='?', default='/tmp/demo-estate')
    parser.add_argument('--tenants', type=int, default=100,
                        help='active tenants per cluster (default 100, so ~200 overall)')
    parser.add_argument('--seed', type=int, default=20260829)
    parser.add_argument('--domain', default='dcs.example.com',
                        help='label domain; the chart writes <domain>/lifecycle')
    args = parser.parse_args()

    estate = Estate(args.outdir, args.tenants, args.seed, args.domain)
    files = estate.build()

    if os.path.isdir(args.outdir):
        shutil.rmtree(args.outdir)
    for rel, body in files.items():
        path = os.path.join(args.outdir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as fh:
            fh.write(body)

    s = estate.stats
    print(f"Wrote {len(files)} files to {args.outdir}\n")
    print(f"  clusters                 2")
    print(f"  tenants                  {s['tenants']}  (+{s['decommissioned_tenants']} decommissioned)")
    print(f"  namespaces               {s['namespaces']}  (+{s['decommissioned_ns']} decommissioned)")
    print(f"    of which devspaces     {s['devspaces']}")
    print(f"    of which egress/CSO    {s['cso']}")
    print(f"    of which mesh planes   {s['mesh']}")
    print(f"  capsules                 {s['capsules']}")
    print(f"  registry mirrors         {s['mirrors']}")
    print(f"  route exceptions         {s['route_exceptions']} granted in tenant-metadata"
          f"  ({s['expired']} expired, {s['expiring']} expiring within 30 days)")
    print(f"                           +{s['route_exceptions_values']} more declared only in a "
          f"namespace values.yaml")
    print()
    print("The sync will report slightly more namespaces than listed above: a service")
    print("mesh names dataplane members that do not otherwise exist, and the walk")
    print("creates them. That is the behaviour being exercised, not a miscount.")
    print(f"\nLoad it:\n  python manage.py sync_gitops --repo-path {args.outdir}")


if __name__ == '__main__':
    main()
