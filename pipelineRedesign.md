# Customer onboarding — analysis and phased redesign

Written after reading every file in `pipelineRepoReferences/`. Nothing here is
implemented yet; this is the design we agreed to settle before touching code.

Names below (`zzz.com`, `dcsc-`, `dcs-namespace-provisioner`) are as they appear
in the reference copies. Where the masking is inconsistent between two files I
flag it rather than assume.

---

## 1. What the pipelines actually do today

### 1.1 Six operations behind two repos

| # | Operation | Repo | Selected by | Script |
|---|---|---|---|---|
| 1 | Create/update namespace | namespace-prov | default path | `scaffold.sh` |
| 2 | Create/update CSO (EgressIP) | namespace-prov | `CSO_CREATE=true` | `scaffold.sh` → `run_scaffold_cso` |
| 3 | Decommission namespace | namespace-prov | `DECOMMISSION=true` | `decommission.sh` |
| 4 | Decommission CSO | namespace-prov | `DECOMMISSION_CSO=true` | `decommission.sh` |
| 5 | Backfill metadata | namespace-prov | `SYNC_METADATA` **CI variable** | `sync-metadata.sh` |
| 6 | Registry mirror | mirror-config | only job in repo | `scaffold-registry-mirror.sh` |

Operation 5 is **out of scope**: it was a one-off backfill for tenants
provisioned before `tenant-metadata.yaml` existed. It stays as-is, is not in the
operation enum, and Phase 1 does not touch it. Worth noting for its own sake
though: it is already driven by a CI variable rather than an input, which is
useful precedent if the payload ever has to move off inputs.

The five in scope are 1–4 and 6.

Every script reads its parameters exclusively from `INPUT_*` environment
variables. The `.gitlab-ci.yml` `variables:` block is the only place
`$[[ inputs.X ]]` appears. That is what makes Phase 1 cheap: the scripts have no
knowledge of GitLab inputs at all, only of environment variables.

### 1.2 Input inventory

- namespace-prov: **25** inputs
- mirror-config: **14** inputs
- shared by name: 5 (`REQUESTER_EMAIL`, `REQUEST_ID`, `REQUESTED_TIMESTAMP`,
  `TENANT_NAME`, `TARGET_CLUSTER`)
- **merged unique: 34**

Against the measured ceiling of **20 changed values per pipeline run on every
path including the web UI**, a merged form is impossible with discrete inputs.
A maximal prod namespace request already changes exactly 20 today — zero
headroom before merging anything or adding HCP.

### 1.3 The shape of a request

`scaffold.sh` runs six stages in order:

```
validate_inputs → prepare_variables → sanity_checks → update_metadata
  → run_scaffold_cso | run_scaffold_project
  → validate_security_policies → sync_cross_namespace_policies → run_git_ops
```

Points that matter for the redesign:

**Names are generated, not supplied.** `prepare_variables` appends a random
4-char suffix (`dcsc-<project>-a1b2`) unless the exact directory already exists.
So the form cannot show the operator the final namespace name — it is decided
inside the pipeline. Same for EgressIP objects (`dcsc-ei-<10 chars>`) and
registry names (`dcsc-<tenant>-registry-<4>-external`).

**Create and update are the same entry point**, distinguished by whether
`${cluster}/${tenant}/${project}` exists on disk (`IS_EXISTING_PROJECT`).

**The update path is much narrower than the create path.** For an existing
project, template generation is skipped entirely to preserve hand edits. Only
these are applied on update:

- the five operator toggles (`managedServices.*.enabled`)
- GPU tier merge
- route exception
- add-namespace-to-mesh
- cross-namespace policy sync

Everything else in `values.yaml` — resource quota, limit ranges, Harbor storage
quota, CVE allowlist, proxy flag, project users, robot accounts — is written
**once, from the template, at creation time** and is unreachable from the
pipeline thereafter.

> This is the structural reason MR review is genuinely needed today, and it
> confirms what you said: "if we are trying to automate, we need to make every
> point of values file customizable." The pipeline is not currently capable of
> the edits ops make by hand. That is a gap the new form can close later, but it
> is **not** a Phase 1 or Phase 2 problem — it is a scaffold-script problem.

**Operators are one-way.** Every toggle is `if INPUT_X == true → set enabled=true`.
There is no branch that sets `false`. A namespace can never have an operator
disabled through the pipeline. Given operators appear in ~4 of 10 requests, this
is worth fixing — but again, in the scripts, not the form.

**One request can rewrite sibling namespaces.** `sync_cross_namespace_policies`
walks every `values.yaml` under the tenant, deletes four
`allowedFlows.crossNamespacePolicies.*` keys from all of them, and re-adds them
to the devspace and CloudNativePG ones. `run_git_ops` then does
`git add "$CUSTOMER_DIR"`. So "one request = one namespace" is not true at the
file level, and OpsDash's request-to-diff correlation should not assume it.

### 1.4 Validation is coupled to the CI form

This is the single most important finding for Phase 1.

`validate_inputs` does not check "is this field filled in". It checks **"is this
field still equal to the placeholder string declared in `.gitlab-ci.yml`"**:

```bash
[[ "$INPUT_REQUEST_ID" == "REQ00000000000XX" ]] && { log_error "..."; exit 1; }
if [[ "$INPUT_COST_CENTER" == "XX/YY0000-00000" ]]; then ... exit 1; fi
[[ "$INPUT_REQUESTED_TIMESTAMP" == "01/04/2026 13:47:48" ]] && { ... exit 1; }
case "$INPUT_REQUESTER_EMAIL" in "projectowner@zzz.com" | ... ) exit 1 ;; esac
```

The same literal is written in two files that have no mechanical link. That
design has already drifted:

| Field | `.gitlab-ci.yml` default | Literal in `scaffold.sh` | Effect |
|---|---|---|---|
| `SIGLUM` | `TDXX` | `"tdxx"` — but the value is **uppercased first** | **Check is dead — confirmed by replay.** |
| `TENANT_NAME` | `tenantName` | *no check at all* | A default-left request creates a tenant literally named `tenantname-a1b2`. The mirror repo does check this; namespace-prov does not. |
| `ARD_LINK`, `REQUESTER_EMAIL` | — | — | Domain differences are masking artefacts in the reference copies, not real drift. Confirmed; no action. |

The siglum case is not a typo I inferred — it is what the two lines do together.
`INPUT_SIGLUM` is normalised with `tr '[:lower:]' '[:upper:]'`, so whatever the
operator typed arrives at the comparison as `TDXX`, and `[[ "TDXX" == "tdxx" ]]`
is false in bash. Replaying the exact two lines:

```
operator typed TDXX   -> normalised TDXX -> ACCEPTED (check does not fire)
operator typed tdxx   -> normalised TDXX -> ACCEPTED (check does not fire)
operator typed TdXx   -> normalised TDXX -> ACCEPTED (check does not fire)
```

Contrast `COST_CENTER`, which uses the same normalisation but whose sentinel
(`XX/YY0000-00000`) is already uppercase, so it fires correctly. The
normalisation is fine; the sentinel is written in the wrong case. Under the
schema this disappears — the field is simply `required`, and case is a
`normalise:` property rather than something a comparison has to survive.

Under a JSON payload there are no placeholders, so these checks become
meaningless anyway. **Sentinel-equality must become presence/emptiness
checking.** That is a real behavioural change, small but not zero, and I would
rather call it out than smuggle it in under "we only changed the way we read".

Net effect is an improvement: three currently-dead checks start working.

### 1.5 Conditional rules already in the code

These are exactly the `showIf` / `requiredIf` rules the form needs. They exist
today only as bash:

| Rule | Source |
|---|---|
| ARD mandatory and non-default **iff** `LIFECYCLE == prod` | `scaffold.sh:104` |
| GPU tier required **iff** `GPU_ENABLED == true`; must be `None` otherwise | `scaffold.sh:129` |
| Route exception allowed **iff** `LIFECYCLE == dev` | `scaffold.sh:137` |
| `REGISTRY_USERNAME`/`SECRET_REF` required **iff** `REGISTRY_AUTH == true` | mirror:82 |
| Deploy-mesh and add-to-mesh are mutually exclusive | `scaffold.sh:327` |
| `TENANT_PROJECT` may not start with `dcsc-ds` or `dcsc-cso` | `scaffold.sh:118` |
| Cost centre may be empty (non-billable) but not the placeholder | `scaffold.sh:55` |
| Prod robot accounts may not have `push` | `scaffold.sh:589` |

### 1.6 Defects found while reading

Ranked by how much they matter to this project.

1. **Decommission cannot be triggered by API.** `decommission-tenant` has
   `rules: - if: '$CI_PIPELINE_SOURCE == "web" && ...'`. `scaffold-tenant` allows
   `web` **and** `trigger`. So any Pages- or OpsDash-driven decommission produces
   a pipeline with no jobs. Must be fixed in Phase 1. Note also that neither job
   matches `api`, which is the source when triggering with a PAT rather than a
   trigger token — Phase 2 needs that added.

2. **`DECOMMISSION` and `DECOMMISSION_CSO` can both be true.** The rule is an
   `||`; `decommission.sh` then branches on `DECOMMISSION_CSO` only. A single
   `operation` enum removes the whole class of problem.

3. **`decommission.sh:363` does `git add "$IPPOOL_FILE"` unconditionally.** Under
   `set -e`, a cluster without `egressip-pool.yaml` fails the run *after*
   directories have already been deleted from the working tree. Nothing is
   pushed, so it is recoverable, but the operator sees a red pipeline on a
   half-done job. Should be `[ -f "$IPPOOL_FILE" ] && git add ...`, matching what
   `scaffold.sh` already does correctly.

4. **`TENANT_DEPLOY_SERVICE_MESH` is unreachable on the create path — confirmed.**
   `sanity_checks` requires `TENANT_PROJECT == "dcsc-${TENANT_NAME}-service-mesh"`,
   but `prepare_variables` has already appended the random suffix. Replaying the
   naming logic across every way an operator could fill the form:

   | tenant dir exists | project typed | computed | expected | result |
   |---|---|---|---|---|
   | no | `dcsc-tenanta-service-mesh` | `dcsc-tenanta-service-mesh-a1b2` | `dcsc-tenanta-a1b2-service-mesh` | mismatch |
   | yes | `dcsc-tenanta-service-mesh` | `dcsc-tenanta-service-mesh-a1b2` | `dcsc-tenanta-service-mesh` | mismatch |
   | no | `dcsc-tenanta-a1b2-service-mesh` | `dcsc-tenanta-a1b2-service-mesh-a1b2` | `dcsc-tenanta-a1b2-service-mesh` | mismatch |
   | yes | *(empty)* | `dcsc-tenanta-a1b2` | `dcsc-tenanta-service-mesh` | mismatch |

   There is no input that satisfies it, and the operator cannot pre-type the
   suffix because it is regenerated on every run. The cause is a missing branch:
   CSO and DevSpace both override project naming in `prepare_variables`
   (`dcsc-cso-…`, `dcsc-ds-…`, no suffix), and mesh does not. The fix is the
   matching `elif`:

   ```bash
   elif [[ "${INPUT_DEPLOY_MESH,,}" == "true" ]]; then
       TENANT_PROJECT="dcsc-${TENANT_NAME}-service-mesh"
   ```

   The only way a mesh exists today is if the directory and its `values.yaml`
   were created by hand in an MR — in which case `IS_EXISTING_PROJECT` is true,
   the check is skipped, and `values-service-mesh.yaml.tpl` is never applied.
   That is consistent with the mesh values being hand-written.

5. **Timestamp formats disagree between the two repos.** namespace-prov wants
   `DD/MM/YYYY HH:MM:SS` and converts to ISO internally; mirror-config wants ISO
   `YYYY-MM-DDTHH:MM:SS` directly and does no validation on it. A merged form
   needs one canonical format — ISO, with the shim rendering the legacy format
   for `scaffold.sh`/`decommission.sh` if we want those scripts untouched.

6. **`EGRESSIP_SUBNET` packs two values into one string** (`x.x.1.0/24(1)IP`)
   and is unpacked with `awk`. Fine as-is; in the schema it should be two fields
   with the shim re-encoding the legacy string.

7. `sync_cross_namespace_policies` runs `yq -i` with only `del()` on namespaces
   that are neither devspace nor CNPG. yq rewrites the file, so unrelated
   namespaces can pick up reformatting diffs, which then satisfy `run_git_ops`'s
   "did anything change" guard.

8. `sync-metadata.sh` writes a metadata file without `siglum`, `gpu_enabled`,
   `active_cso` or `active_registry_mirrors`, and `decommission.sh` reads
   `.active_sub_tenants`, which nothing ever writes.

9. mirror-config hardcodes `@zzz\.com$` in the email regex while the error text
   says `@zzzz.com`; namespace-prov does not check the domain at all.

10. `.gitlab/auto-update.yml` is `include`d but was not in the bundle, so I have
    not reviewed it.

---

## 2. The idea that makes all three phases work

One file, in the customer onboarding repo, that is the only place a field is
ever declared:

```
dcs-customer-onboarding/
  request-schema.yaml      <-- single source of truth
  pipeline-scripts/
    load-payload.sh        <-- new; schema + JSON -> INPUT_* env
    scaffold.sh            <-- unchanged
    decommission.sh        <-- unchanged
  pages/                   <-- new; static form, reads the schema
```

Three consumers, one definition:

| Consumer | Reads it | When |
|---|---|---|
| Pipeline (`load-payload.sh`) | at run time, from the checkout | every run |
| GitLab Pages form | at build time, converted to `schema.json` | on merge to main |
| OpsDash | over the GitLab API, like it already fetches the GitOps repo | on sync |

Because OpsDash *fetches* the schema rather than vendoring it, a new field
appears in OpsDash with no OpsDash release. That is the "opsdash should not be a
touch point at all" requirement, satisfied structurally.

### 2.1 Schema shape

```yaml
version: 1

operations:
  namespace.create:
    title: New namespace
    job: scaffold-tenant
    fields: [request_id, requester_email, requested_at, tenant_name, ...]
  namespace.decommission: { title: Decommission namespace, job: decommission-tenant, fields: [...] }
  cso.create:           { ... }
  cso.decommission:     { ... }
  mirror.create:        { title: Registry mirror, job: scaffold-registry-mirror, fields: [...] }

groups:
  - { id: request,   title: Request details }
  - { id: placement, title: Tenant and cluster }
  - { id: features,  title: Optional features }
  - { id: operators, title: Operators }

fields:
  requested_at:
    group: request
    type: datetime
    required: true
    env: INPUT_REQUESTED_TIMESTAMP
    encode: "DD/MM/YYYY HH:mm:ss"      # what the legacy script expects
    label: Request time from ITSM

  siglum:
    group: request
    type: string
    required: true
    normalise: upper                   # replaces the tr | sentinel pair (§1.4)
    env: INPUT_SIGLUM

  tenant_name:
    group: placement
    type: string
    required: true
    normalise: lower
    env: INPUT_TENANT_NAME
    source: { index: tenants, by: [target_cluster] }   # picklist, free text allowed

  gpu_enabled:
    group: features
    type: boolean
    default: false
    env: INPUT_GPU_ENABLED

  gpu_tier:
    group: features
    type: enum
    options: [standard, dedicated.h200, dedicated.h200.1g.18gb]
    env: INPUT_GPU_TIERS
    showIf:     { gpu_enabled: true }
    requiredIf: { gpu_enabled: true }
    absentValue: "None"                # what to send when hidden

  ard_link:
    group: request
    type: url
    env: INPUT_ARD_LINK
    showIf:     { lifecycle: prod }
    requiredIf: { lifecycle: prod }

  route_exception:
    group: features
    type: boolean
    default: false
    env: INPUT_ROUTE_EXCEPTION
    showIf: { lifecycle: dev }
```

The `env:` key is what keeps the promise that we are "only changing the way we
read". `absentValue:` is what lets a hidden field still satisfy a legacy script
that expects a literal `None`.

Adding a field later = one block in this file + whatever the scaffold script
needs to do with the new `INPUT_*`. Pages and OpsDash adjust themselves.

---

## 3. Phase 1 — collapse the inputs

**Feasible, no blockers.** Estimated: one new 80-line script, one rewritten
`.gitlab-ci.yml` per repo, one added line at the top of each of the three
scripts. `scaffold.sh`, `decommission.sh` and
`scaffold-registry-mirror.sh` bodies are otherwise untouched.

### 3.1 The CI interface becomes two variables

```yaml
spec:
  inputs:
    OPERATION:
      description: "Which operation to run."
      options: [namespace.create, namespace.decommission, cso.create, cso.decommission, mirror.create]
      default: namespace.create
    REQUEST_PAYLOAD:
      description: "The request as a JSON object. Generated by the onboarding form."
      default: "{}"
```

`OPERATION` must stay a separate value rather than living inside the JSON,
because `rules:` are evaluated at pipeline-creation time and GitLab cannot see
inside the payload string. That is also the fix for defect #2.

**Both stay inputs.** My earlier lean towards a CI variable was based on one
concrete worry: `$[[ inputs.X ]]` is interpolated into the CI YAML as text
*before* the YAML is parsed, and a JSON payload is full of `"`, `{`, `:` and `,`
— all YAML-significant. That worry is already answered by your own probe on
18.1.4, where `REQUEST_JSON` round-tripped through an input intact. Measured
beats reasoned, so: inputs.

Inputs are also the better choice on the merits once that risk is gone:
`OPERATION` gets server-side enum enforcement from `options:` for free, both
values render as described, labelled fields on the Run-pipeline page rather than
bare key/value rows, and the whole interface stays declared in one place.

Two changed inputs per run against a cap of 20. Room for HCP and whatever comes
after.

**One thing left to measure**, and it is the last open question on Phase 1: the
maximum size of an input value. Today's payloads are 600–900 bytes, but they
will grow — user lists, CVE allowlists, comma-separated image lists. Worth
pushing 4 KB and 16 KB payloads through the same probe kit before we commit. If
16 KB passes, the question is closed permanently. If it fails low, `REQUEST_PAYLOAD`
alone moves to a variable and `OPERATION` stays an input — a one-line change,
and `SYNC_METADATA` already shows that path works.

### 3.2 `load-payload.sh`

Sourced as the first line of each script:

```bash
source "$(dirname "$0")/load-payload.sh"
```

It:

1. reads `request-schema.yaml` and `$REQUEST_PAYLOAD` with `yq` — already in
   `pipeline-tools:1.1.3`, so **no new dependency and nothing to pull in an
   airgapped runner**; `yq` v4 parses JSON natively
2. rejects any key in the payload not declared in the schema (typo protection)
3. for each field in the selected operation: takes the payload value, else the
   schema `default`, else `absentValue`
4. **enforces `type` and `options` from the schema**
5. applies `encode:` where a legacy script wants a legacy format
6. `export`s `INPUT_*`

It runs in the same shell as the calling script — no `eval`, no dotenv artifact,
no artifact-variable limits to worry about.

### 3.3 The one real drawback of Phase 1

**Collapsing to a JSON string deletes GitLab's own type and enum enforcement.**
Today GitLab guarantees server-side that `LIFECYCLE ∈ {dev, prod}`, that
`ROUTE_EXCEPTION` is a boolean, and that `TARGET_CLUSTER` is a declared cluster.
A JSON blob has none of that. If `load-payload.sh` does not re-implement it,
Phase 1 is a **net loss in safety** — a typo'd `TARGET_CLUSTER` would today be
rejected by GitLab and would tomorrow silently `mkdir` a new top-level cluster
directory.

So step 4 above is not optional polish; it is the load-bearing part of the
phase. I will treat schema-driven type/enum enforcement as a hard requirement of
Phase 1, not something deferred to the form. The form is a convenience; the shim
is the gate.

Secondary drawbacks, all acceptable:

- Sentinel checks become presence checks (§1.4). Small behaviour change, net
  improvement, must be documented in the MR.
- The web-UI break-glass path gets worse for a human typing by hand: one JSON
  blob instead of 25 labelled fields. Mitigated by the Pages form arriving in
  Phase 2, and by `load-payload.sh` producing a clear echo of the resolved values
  at the top of the job log.
- Pipeline schedules or bookmarks that set individual inputs stop working. Worth
  checking whether any exist before we merge.

### 3.4 Also folded into Phase 1

- add `trigger` and `api` to the decommission job's rules (defect #1)
- guard `git add "$IPPOOL_FILE"` (defect #3)
- one canonical ISO timestamp in the payload, legacy format rendered by `encode:`
  (defect #5)
- `egressip_subnet` + `egressip_count` as two fields, legacy string re-encoded
  (defect #6)

---

## 4. Phase 2 — the GitLab Pages form

**Feasible with one thing that needs measuring first.**

### 4.1 Build

A `pages` job in the onboarding repo:

```yaml
pages:
  stage: deploy
  script:
    - mkdir -p public
    - yq -o json request-schema.yaml > public/schema.json
    - cp -r pages/* public/
  artifacts: { paths: [public] }
  rules: [ if: '$CI_COMMIT_BRANCH == "main"' ]
```

The form itself is plain HTML + one JS file + one CSS file. No bundler, no npm,
no CDN — the same airgapped constraint OpsDash builds under, and here it is
easier because there is no framework to vendor. The whole site is three static
files plus generated `schema.json`.

Flow: pick operation → render only that operation's fields, grouped, with
`showIf` evaluated live → validate against the same rules the shim will enforce
→ show the assembled JSON → submit.

### 4.2 The generated index — no more "note it down beforehand"

I had this wrong in the first draft. I wrote that a static form cannot know repo
state, and that this was the structural reason Phase 3 had to exist. It is not
true, because **the namespace-prov repo _is_ `dcs-customer-instances`**:
`scaffold.sh` resolves `${cluster}/${tenant}/${project}` relative to the CI
checkout and pushes its branch back to `$CI_PROJECT_PATH`. (The mirror repo is
the separate one — it clones customer-instances into `/tmp`.)

So the `pages` job is already standing in a full checkout of every cluster,
tenant and namespace. It can emit an index for free:

```yaml
- |
  yq -n -o json '[]' > public/index.json
  for cluster in qa-w1; do
    for meta in "$cluster"/*/tenant-metadata.yaml; do ... done
  done
```

giving the form `{cluster: {tenant: [namespace, ...]}}`, built from
`tenant-metadata.yaml` with the directory tree as the fallback for legacy
tenants. Schema fields then declare where their options come from:

```yaml
  tenant_name:
    type: string
    source: { index: tenants, by: [target_cluster] }   # picklist + free text
  tenant_project:
    type: string
    source: { index: namespaces, by: [target_cluster, tenant_name] }
    showIf: { mode: update }
```

This directly addresses the point you raised: *"for updates, operators must note
down the tenant and namespace name before triggering the pipeline manually."*
They stop noting anything down — they pick the cluster, then the tenant, then
the namespace, each list narrowed by the last. And because the form now knows
whether the tenant exists, it can ask the create-or-update question explicitly
up front rather than letting the operator discover the answer from a failed
pipeline.

It also kills the worst failure mode in `prepare_variables`: *"You cannot leave
the Project Name empty/default for an existing tenant"* becomes unreachable,
because an existing tenant never renders an empty project field.

**Freshness.** The index is as of the last merge to `main` — which is exactly
when tenants and namespaces come into existence, since they are created by
merging the scaffold branch. The one stale window is between a scaffold pipeline
running and its MR being merged. OpsDash reads `main` too, so it has the same
window; neither is better. Worth showing the index's commit SHA and timestamp in
the form footer so an operator can see how current it is.

### 4.3 The open question: can the browser trigger the pipeline?

Three candidate mechanisms:

| Mechanism | Endpoint | `CI_PIPELINE_SOURCE` | Problem |
|---|---|---|---|
| Trigger token in the page's JS | `POST /trigger/pipeline` | `trigger` | Token is readable by anyone who can load the page. Even with Pages access control, it is a shared secret in client-side source, and the audit trail says "the token", not "who". |
| Operator's PAT in `localStorage` | `POST /projects/:id/pipeline` | `api` | Real per-person audit trail. Needs each op to mint a PAT once. **Needs a CORS check.** |
| No trigger — "Copy request JSON" | n/a | `web` | Always works. Two steps: copy, then paste into Run pipeline. |

**I recommend building (3) unconditionally and (2) on top of it.** (3) is the
guaranteed floor and is already a large win — one paste instead of 25 fields,
with client-side validation. (2) is the nice path if CORS permits.

**Probe needed, and it is a five-minute one.** From a browser on your GitLab,
open the console on any page from a *different* origin than the API and run a
cross-origin `POST /api/v4/projects/:id/pipeline` with a `PRIVATE-TOKEN` header.
If the preflight is refused, (2) is out and we ship (3). I will write the probe
the same way as the input-limit kit so the result is unambiguous. This does not
block anything before it — the form, the schema and the validation are identical
either way; only the submit button changes.

### 4.4 Drawbacks

- **The final name is unknown at submit time, and that is fine.** Confirmed: the
  operator has no use for the generated suffix at trigger time. The form should
  not pretend to predict it — it should say the suffix is generated and move on.
  What the operator *does* need is covered below.
- **Access control.** Pages must be restricted to project members, otherwise the
  form (and, in option 1, the token) is open to anyone who can reach the URL.
- **Schema and form can drift from the scripts** if someone adds an `INPUT_*` to a
  script without adding it to the schema. Cheap fix: a CI job that greps the
  scripts for `INPUT_[A-Z_]*` and fails if any is missing from `request-schema.yaml`.
  I would add that in Phase 1.

---

## 5. Phase 3 — OpsDash as an add-on

**Feasible, and this is where the read-only rule needs an explicit decision.**

OpsDash fetches `request-schema.yaml` from the onboarding repo the same way it
already fetches the GitOps repo, and renders the same form with the existing Vue
app. Nothing about the schema is vendored, so new fields need no OpsDash change.

**What OpsDash adds over Pages is smaller than I first claimed.** Once the Pages
job emits `index.json` (§4.2), the tenant/namespace picklists and the
create-vs-update question are solved on the static site too. That is not a
disappointment — it is the right outcome, because it means the Pages route is
fully sufficient on its own and OpsDash genuinely is optional. Which is the
architecture you asked for.

What is left, and it is real but it is context rather than capability:

- pre-fill siglum, cost centre and requester from the tenant's existing metadata,
  so an update request restates nothing
- show the namespace's current quota, operators, GPU tier and Harbor settings
  *beside* the form, so the operator can see what they are changing from
- link the resulting branch/MR back to the tenant afterwards, closing the loop
  that today ends at "please create a Merge Request"
- flag the stale window — OpsDash syncs on its own schedule and can say "this
  tenant has an open scaffold branch not yet merged", which a build-time index
  cannot

**The read-only decision.** The backend brief was strict: no write paths, no
mutation endpoints, no pipeline-triggering features. Phase 3 as described
contradicts that. Three ways to resolve it, in the order I would pick them:

1. **OpsDash never posts.** It builds and validates the payload, then hands it
   off — "Copy JSON" plus a deep link to the Pages form pre-seeded via the URL
   fragment, or to the Run-pipeline page. Read-only stays intact and OpsDash
   remains a pure add-on: if it is down, Pages is unaffected and vice versa.
2. **OpsDash posts from the browser with the operator's PAT.** Server stays
   read-only; the write happens from the client under the operator's identity.
   Depends on the same CORS answer as Phase 2.
3. **OpsDash posts server-side with a service token.** Best UX, but it makes
   OpsDash hold a credential that can write to the GitOps repo, and it puts a
   mutation endpoint in an app that was explicitly built without one.

I recommend (1) for the first cut, with (2) as a follow-up if the CORS probe
comes back clean. (3) I would avoid unless you want OpsDash to become part of
the ecosystem rather than an add-on to it — which is the opposite of the stated
goal.

### 5.1 Drawback specific to Phase 3

Two form implementations of the same schema (vanilla JS on Pages, Vue in
OpsDash) means two places for the `showIf` evaluator and the validator to be
written. They can drift. Mitigations: keep the evaluator in one small
dependency-free `.js` file that both load — OpsDash can serve a copy fetched
during sync — or accept the duplication and cover it with a shared fixture of
payload/expected-validity pairs that both must agree on. I lean towards the
shared file; it is about 100 lines.

---

## 6. Order of work

| Phase | Deliverable | Blocked by |
|---|---|---|
| 1a | `request-schema.yaml` covering all 34 merged fields | nothing |
| 1b | `load-payload.sh` with type/enum enforcement | 1a |
| 1c | Rewritten `.gitlab-ci.yml` for both repos, + defects 1,2,3,5,6 | 1b |
| 1d | Drift-check CI job (`INPUT_*` in scripts ⊆ schema) | 1a |
| 2a | Probe kit: input value-size ceiling + cross-origin POST | nothing — parallel with 1 |
| 2b | `index.json` generation in the `pages` job | nothing |
| 2c | Static form + `pages` job, "Copy JSON" submit | 1a, 2b |
| 2d | Direct trigger, if 2a permits | 2a, 2c |
| 3a | OpsDash fetches schema during sync | 1a |
| 3b | Schema-driven form in OpsDash, hand-off submit | 3a |
| 3c | Direct trigger from OpsDash, if 2a permits | 2a, 3b |

Phase 1 is independently valuable: even if Pages never ships, it removes the
20-input ceiling, unblocks merging the two repos, and fixes three dead
validation checks and a decommission path that cannot be automated.

## 7. Settled

| Question | Answer | Consequence |
|---|---|---|
| Masked domains — drift or artefact? | Artefact | No action; only the siglum check is really dead |
| `.gitlab/auto-update.yml` | Out of scope for now | Not reviewed; Phase 1 must not touch its `include:` |
| `sync-metadata` | Out of scope — it was a one-off backfill for tenants provisioned before `tenant-metadata.yaml` existed | Dropped from the operation enum. The job and its `SYNC_METADATA` variable stay exactly as they are, untouched by Phase 1. |
| Pipeline schedules / saved runs | None — always a manual trigger | No migration concern; Phase 1 can change the input surface in one merge |
| `REQUEST_PAYLOAD` input or variable | **Input**, per the probe (§3.1) | One open measurement: input value-size ceiling |
| Suffix visibility to the operator | Not needed at trigger time | Form states it is generated; no prediction attempted |
| Create vs update | Operator must know *before* triggering, and today has to note names down by hand | The generated index (§4.2) removes the manual step entirely — the single largest ergonomic win in Phase 2 |

Remaining open, neither blocking Phase 1:

1. Input value-size ceiling (§3.1) — one probe.
2. Cross-origin POST to the API from the Pages origin (§4.3) — one probe.

Both are additive to the probe kit that settled the input-count question.
