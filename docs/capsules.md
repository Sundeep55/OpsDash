# Capsules

A **capsule** is a delegated slice of a tenant. Its users create their own
namespaces, drawing on one shared resource quota, and the estate deliberately
does not track those namespaces — only the capsule and the quota it owns.

That last sentence is the whole design. A capsule's quota is the entire
allocation its users draw on, not a total of anything the dashboard can see
underneath it, which is why capsules are **counted** everywhere and never
resource-summed into namespace totals.

## Why "capsule" and not "sub-tenant"

The pipeline calls it a sub-tenant: the request field is `sub_tenant_name`, the
metadata key is `active_sub_tenants`, and the decommission flag is
`INPUT_DECOMMISSION_SUB_TENANT`. That vocabulary is kept on the pipeline side.

The dashboard calls it a capsule because a tab called *Tenants* next to one
called *Sub-tenants* collapses the moment anyone says them out loud — which is
the exact confusion the feature had to avoid.

## How the sync recognises one

A capsule directory looks like a namespace directory. Both sit at
`<cluster>/<tenant>/<name>/values.yaml` and both are named `dcsc-*`. The only
discriminator is the top-level block:

| Block | Means |
|---|---|
| `namespace-provisioner` | a namespace (`GITOPS_PROVISIONER_KEY`) |
| `tenant-provisioner` | a capsule (`GITOPS_CAPSULE_KEY`) |

Because per-file detection is order-dependent — `Chart.yaml` and `templates/`
would be read before the values file that identifies the directory — the walk
does a **first pass** (`_identify_capsules` in `dashboard/gitops/__init__.py`)
that opens only values files, far enough to read their top-level keys, and
records which directories are capsules. Dispatch is then per directory, not per
file. Without that pass a capsule produced a phantom `Namespace` row that
something else had to clean up.

## What is parsed

`dashboard/gitops/parsers/capsule.py`, from the `tenant-provisioner` block:

| Source | Becomes |
|---|---|
| `requiredLabels` / `additionalLabels` — `lifecycle` or `env` | `Capsule.lifecycle` |
| `requiredLabels.siglum` | `Capsule.siglum`, falling back to the tenant's |
| `additionalLabels.cost_center` | `Capsule.cost_center` |
| `additionalAnnotations.tenant_owner` | `Capsule.requester` |
| `globalEgressIpName` | `Capsule.global_egress_ip_name` |
| `resourceQuota` | the quota columns, **stored verbatim** |
| `harborOnboardingConfig` | `harbor_enabled`, `harbor_storage_quota_gb` |
| `project_owner_config` / `project_user_config` | `UserAccess` rows, plus the JSON columns |
| everything else | `Capsule.config`, verbatim |

Label lookup ignores the domain prefix: the chart writes
`dcs.<domain>/lifecycle`, not `lifecycle`. Matching the bare name found nothing
and every capsule fell through to unassigned — the same bug the namespace parser
had, and the reason `_label()` exists in both.

Quota values are **not** normalised. `"16"`, `"64Gi"` and `"1000Mi"` mean
different things and the repo is inconsistent about which it uses; normalising
would lose the distinction between a request and a limit expressed in different
units.

`Capsule.config` holds the rest of the block untouched, so a key added to the
capsule chart appears on the detail page with no dashboard change. The detail
page renders it through the same `DetailSection` component the namespace page
uses — the descriptors are *derived* rather than declared, because a capsule's
blocks are whatever the chart carries.

### Fields that come from tenant-metadata.yaml

The request ticket, requester and lifecycle recorded under `active_sub_tenants`
are **deferred to the end of the walk** (`_apply_capsule_metadata`). File order
is arbitrary, and `tenant-metadata.yaml` is routinely read before the values file
that creates the row — writing inline silently dropped the ticket.

Metadata alone never creates a capsule. An entry left behind after a
decommission would otherwise resurrect one.

## Access

`UserAccess` points at a namespace **or** a capsule (nullable FKs, the same shape
`CustomResource` uses). Capsule membership used to live only in JSON columns, so
the Users directory, the user detail page and the siglum view could not see it —
someone owning three capsules and no namespaces appeared to have no access at
all.

`Capsule.owners` / `.users` are kept in step for the detail page to render
without a join. Both are written from one call to `read_access_lists()` in the
same function, so they cannot disagree with the `UserAccess` rows.

## Route exceptions

Deliberately not modelled. A `RouteException` hangs off a `Namespace`, and a
capsule is not one; the capsule chart ships `routeException.enabled: false` and
nothing writes it. `request-schema.yaml` offers the field, so revisit when a
capsule actually carries a grant — adding a second model and a second banner
query for a case that does not occur would be half-building it.

## Adding a capsule field

1. Add the key to the chart.
2. If nothing filters or sorts on it, **stop** — it already appears on the detail
   page via `Capsule.config`.
3. If something does, add a column on `Capsule`, read it in
   `parse_capsule_values`, expose it in `CapsuleSerializer`, and make a
   migration.

Step 2 is the usual answer. The generic path exists so the chart can grow
without a dashboard release.

## Pipeline operations

`capsule.create`, `capsule.update` and `capsule.decommission`, all using
`sub_tenant_name`. Create and update run `scaffold-capsule.sh`; decommission runs
`decommission.sh` with `INPUT_DECOMMISSION_SUB_TENANT=true`.

All three must appear in the `OPERATION` options in `.gitlab-ci.yml` — GitLab
rejects an input value not in that list, so an operation missing there cannot be
run at all. `tools/check-schema-drift.sh` compares the two and fails the merge
request if they disagree.
