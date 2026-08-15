# Extending the onboarding pipeline

## What you actually have to touch

There are 30-odd files here, which looks like a lot. Almost none of them are
touch points. For the common changes:

| To do this | Edit | Everything else |
|---|---|---|
| Add a field | `request-schema.yaml` + the script that uses its `INPUT_*` | **2 files.** The form, the payload builder, the validator, the picklists and OpsDash all follow on their own. |
| Add an option to an enum | `request-schema.yaml` (+ a template block if the value maps to one) | 1 file |
| Add a validation rule | `request-schema.yaml` | 1 file |
| Add a new operation | `request-schema.yaml`, `.gitlab-ci.yml`, one new script | 3 files |
| Change the look of the form | `pages/style.css` | 1 file |

Nothing in `pages/` is edited to add a field. The form is generated from the
schema at page load: groups become sections, `show_if` decides what is on
screen, `options` becomes a dropdown, `source` becomes a picklist.

**The one optional touch point is `tools/cases.json`** — add a case when you add
a rule you care about. It is not required for the field to work; it is how you
find out later if someone breaks it. It used to be two files asserting
overlapping rules, which was a genuine trap; it is one file now, read by both
the shell runner and the browser page.

Everything else is either the machine (five pipeline scripts, four form files)
or a safety net that runs itself in CI (`check-schema-drift.sh`,
`test-cases.sh`).

## Recipes

1. [Add a field to an existing request](#1-add-a-field)
2. [Add a field that only sometimes applies](#2-add-a-conditional-field)
3. [Add a whole new option to an existing feature](#3-add-an-option)
4. [Add a new operation](#4-add-an-operation)

The rule underneath all of them: **`request-schema.yaml` is the only place a
field is declared.** The pipeline, the GitLab Pages form and OpsDash all read
it. Adding a field in one place makes it appear on every surface; adding it
anywhere else makes it appear on none of them.

`tools/check-schema-drift.sh` runs on every merge request and fails if a script
reads an `INPUT_*` that the schema does not declare, so the rule is enforced
rather than merely documented.

---

## 1. Add a field

Say the provisioner chart grows a backup schedule.

### Declare it

In `request-schema.yaml`, under `fields:`:

```yaml
  backup_schedule:
    group: features
    label: Backup schedule
    description: Cron expression for nightly backups. Leave empty to disable.
    type: string
    env: INPUT_BACKUP_SCHEDULE
    default: ""
```

### Offer it

Add the name to the operations that should show it:

```yaml
  namespace.create:
    fields:
      - ...
      - backup_schedule
```

A field that exists but is offered by no operation is exported with its default
and never asked for. That is deliberate — it is how `cost_center` stays out of a
decommission request without disappearing from the schema.

### Use it

In `pipeline-scripts/scaffold-namespace.sh`:

```bash
if [[ -n "$INPUT_BACKUP_SCHEDULE" ]]; then
    yq e -i ".dcs-namespace-provisioner.backupConfig.schedule = strenv(INPUT_BACKUP_SCHEDULE)" "$VALUES_FILE"
fi
```

### Check it

```bash
./tools/check-schema-drift.sh
./tools/test-cases.sh
```

That is the whole procedure. The Pages form and OpsDash pick the field up with
no change to either.

### Field properties worth knowing

| Property | Notes |
|---|---|
| `env` | **Required.** The variable the scripts read. |
| `type` | `string`, `boolean`, `integer`, `enum`, `email`, `url`, `datetime` |
| `options` | `enum` only. Enforced — this is what replaced GitLab's server-side `options:`. |
| `default` | Used when the operator did not supply the field. |
| `required` | The operator must *supply* it. A required field ignores its own `default`. |
| `allow_empty` | With `required`: the key must be present but `""` is a real answer. |
| `normalise` | `lower` or `upper`. Do not do this in the script. |
| `pattern` | POSIX ERE, checked when the value is non-empty. |
| `deny_prefix` | List of prefixes the value may not start with. |

**On `required` vs `default`:** they do not combine. `required` means presence
in the payload, so a required field never falls back to its default — a
`default` on a required field is only a pre-selection for the form. If a field
has a sensible default, it is not required; if the request is meaningless
without it, it is.

This distinction has teeth. `gpu_tier` defaults to the literal `"None"` that the
scaffold script wants when GPU is off. When `required` meant "ends up non-empty",
*GPU on with no tier chosen* satisfied its own requirement using the sentinel for
absence, and the request went through.

### Naming

Field names are what operators and the form see; `env` is what the scripts see.
They do not have to match — `requested_at` is `INPUT_REQUESTED_TIMESTAMP` — but
both follow the same rules:

- **Say what the value holds.** `images` holds a list, so it is not `image_name`.
  `egressip_allocation` carries a subnet *and* a count, so it is not
  `egressip_subnet`.
- **Booleans read as predicates or `*_ENABLED`.** `registry_needs_credentials`, not
  `registry_auth`. `gpu_enabled`, not `gpu`.
- **No abbreviations.** `JOIN_SERVICE_MESH`, not `ADD_NS_TO_MESH`.
- **No filler.** The five operator toggles are `INPUT_<NAME>_OPERATOR`; the
  `_SERVICES` suffix they used to carry meant nothing.
- **Matched pairs spell alike.** `INPUT_CREATE_CSO` / `INPUT_DECOMMISSION_CSO`,
  both verb-first.
- **Follow the artifact where the artifact has a name.** `INPUT_HARBOR_PROJECT`
  stays "project" because that is Harbor's own word for the thing.

Internal variables computed *inside* a script are a separate matter and are
deliberately left alone. `scaffold-namespace.sh` reads `INPUT_NAMESPACE_NAME`
into a variable called `TENANT_PROJECT`, because what it writes out is a
`dcs.zzz.com/tenant_project` label and a `project_namespace` key. The boundary
between the two names is the point at which an operator's request becomes a
Kubernetes artifact.

---

## 2. Add a conditional field

Fields that only apply sometimes use `show_if` and `required_if`:

```yaml
  backup_bucket:
    group: features
    label: Backup bucket
    type: string
    env: INPUT_BACKUP_BUCKET
    default: ""
    absent_value: ""
    show_if:     { backup_enabled: "true" }
    required_if: { backup_enabled: "true" }
```

- **`show_if`** — every pair must match or the field is hidden. A hidden field is
  never required, and takes its `absent_value` (falling back to `default`).
- **`required_if`** — same shape; makes the field required only when it matches.
- **`absent_value`** — what a hidden field sends. Use it when a script expects a
  specific literal rather than an empty string: `gpu_tier` sends `"None"`
  because `validate_inputs` used to demand exactly that.

Conditions may chain. `registry_username` is shown only when
`registry_needs_credentials` is true, and that field is itself hidden for the
internal replication types — so choosing `dcs-internal` hides both. The shim
resolves conditions to a fixed point, so you do not have to order them.

Two constraints the drift check enforces:

- a `show_if` may only reference a declared field;
- if an operation offers a field, it must also offer whatever that field's
  `show_if` depends on — otherwise the condition silently evaluates against a
  default the operator never saw.

---

## 3. Add an option

Adding a GPU tier, a cluster, or a registry provider is usually two edits.

```yaml
  gpu_tier:
    options: ["standard", "dedicated.h200", "dedicated.h200.1g.18gb", "dedicated.b200"]
```

...plus whatever the value means. For a GPU tier that is a block in
`customers-templates/values-gpuconfig.yaml.tpl` keyed by the option string,
because `run_scaffold_project` looks the tier up by name:

```bash
yq eval -i '. *= load(strenv(GPU_TPL_PATH)).[strenv(INPUT_GPU_TIER)]' "$VALUES_FILE"
```

For a new cluster, add it to `target_cluster.options` **and** create the
`<cluster>/egressip-pool.yaml` the EgressIP path expects.

---

## 4. Add an operation

An operation is a distinct kind of request — a new job, or a meaningfully
different set of fields against an existing script.

### Declare it

```yaml
  namespace.migrate:
    title: Namespace — migrate to another cluster
    job: migrate-namespace
    sets:
      INPUT_MIGRATE: "true"
    fields:
      - request_id
      - requester_email
      - requested_at
      - target_cluster
      - tenant_name
      - namespace_name
```

`sets:` is for values derived from the operation rather than supplied by the
operator. This is what replaced the old `CSO_CREATE` / `DECOMMISSION` /
`DECOMMISSION_CSO` booleans, which a human could set in combinations nothing
handled.

Reuse existing field names wherever the meaning is the same. Five fields are
shared by every operation today; a sixth kind of request should not invent a
second spelling of "requester".

### Add it to the enum

In `.gitlab-ci.yml`, under `spec.inputs.OPERATION.options`. GitLab enforces this
list server-side, so it is the one piece of validation that still happens before
any script runs.

### Add the job

```yaml
migrate-namespace:
  stage: scaffold
  extends: .base-job
  script:
    - chmod +x ./pipeline-scripts/*.sh
    - ./pipeline-scripts/migrate-namespace.sh
  rules:
    - if: '$OPERATION != "namespace.migrate"'
      when: never
    - if: '$CI_PIPELINE_SOURCE == "web"'
    - if: '$CI_PIPELINE_SOURCE == "trigger"'
    - if: '$CI_PIPELINE_SOURCE == "api"'
```

All three sources matter. `web` is the Run-pipeline page, `trigger` is a trigger
token, `api` is a POST with a personal access token — the form uses one of the
latter two. A job missing `api` and `trigger` produces a pipeline with no jobs
in it, which is what used to happen to decommission requests.

### Write the script

```bash
#!/bin/bash
set -e
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_HERE}/common.sh"
source "${_HERE}/load-payload.sh"

enable_debug_if_requested
# INPUT_* are populated and validated by this point.
```

Do not write a `validate_inputs`. Presence, type, enum, format and case belong
in the schema. What belongs in the script is anything that needs the repository
on disk — does this directory exist, is this name already taken, is this state
consistent. That is the split, and keeping a second copy of the syntax rules in
a script is what produced a siglum check that could never fire.

---

## Before you commit

```bash
./tools/check-schema-drift.sh     # schema and scripts still agree
./tools/test-cases.sh             # the gate still enforces what it claims to
bash -n pipeline-scripts/*.sh     # nothing is syntactically broken
```

The first two also run as the `validate-schema` job on any merge request
touching the schema, the scripts, the form or the tools.

### If you changed a validation rule

Add a case to `tools/cases.json`:

```json
{ "name": "backup bucket is required once backups are on",
  "operation": "namespace.create",
  "payload": { "...": "...", "backup_enabled": "true" },
  "expect": "reject",
  "message": "backup_bucket" }
```

`expect` is `accept` or `reject`. `message` (optional) is a substring the
rejection must mention. `exports` (optional) asserts the `INPUT_*` values the
scripts would end up reading:

```json
  "exports": { "INPUT_BACKUP_BUCKET": "", "INPUT_GPU_TIER": "None" }
```

One file, two runners. `tools/test-cases.sh` runs it through the shell shim and
checks all three things. `pages/parity.html` runs the same file through the
browser engine and checks `expect` — the browser has no environment to export
into and words its errors for a human, so `message` and `exports` are shim-only.

Both must agree. That is the point: the shim is the gate, and the browser copy
exists so an operator learns about a mistake while typing rather than from a red
pipeline. A rule only one of them enforces is a rule the operator meets twice or
never. Merging the two case files that used to exist immediately exposed three
such rules that the browser was silently letting through.

This suite has earned its keep: it caught two defects on its first run, one of
which made every `required: true` in the schema invisible, so nothing was
required at all.
