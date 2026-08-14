# `pipeline-scripts/`

What each file is, in the order a request passes through them.

| File | Sourced or run | One line |
|---|---|---|
| `common.sh` | sourced first | `log_info`, `log_error`, `banner`, `enable_debug_if_requested` |
| `load-payload.sh` | sourced second | Turns `OPERATION` + `REQUEST_PAYLOAD` into the `INPUT_*` variables everything else reads |
| `scaffold-namespace.sh` | run | Creates or updates a namespace, or creates a tenant EgressIP object |
| `scaffold-mirror.sh` | run | Adds registry replication rules to an existing namespace |
| `decommission.sh` | run | Retires a namespace or an EgressIP object |
| `validate-mr-permissions.sh` | run | Blocks prod robot accounts with `push`, on merge requests to `main` |

---

## `common.sh`

The logging helpers. They were duplicated verbatim in all three scripts back
when the registry mirror lived in its own repository; this is the one copy.

`enable_debug_if_requested` turns on `set -x` when `DEBUG=true`, which is how
every script used to open.

## `load-payload.sh`

The only thing between a request and the filesystem.

Reads `request-schema.yaml`, resolves the payload against it, and exports the
`INPUT_*` variables the other scripts have always read. Those scripts do not
know it exists — they still just read environment variables.

It does the work that GitLab used to do server-side when there were 25 separate
CI inputs: presence, type, enum membership, format, case normalisation, and the
cross-field rules (`show_if` / `required_if`). Collapsing to one JSON string
removed GitLab's enforcement, so this puts it back. Without it a mistyped
`target_cluster` that GitLab would have rejected outright reaches `mkdir -p`
and quietly creates a new top-level cluster directory.

It is also where the MyITSM timestamp is reassembled: the operator pastes
`DD/MM/YYYY HH:MM:SS`, every script receives ISO 8601.

Sourced rather than executed, so it exports into the calling script's own shell
— no `eval` of generated text, no dotenv artifact.

Covered by `tools/test-load-payload.sh`. Change it and run that.

## `scaffold-namespace.sh`

Was `scaffold.sh`. Handles `namespace.create` and `cso.create`; the difference
arrives as `INPUT_CREATE_CSO`, which the operation sets rather than the
operator.

```
prepare_variables → sanity_checks → update_metadata
  → run_scaffold_cso | run_scaffold_project
  → validate_security_policies → sync_cross_namespace_policies → run_git_ops
```

Two things worth knowing before you edit it:

- **Names are generated here, not supplied.** `prepare_variables` appends a
  random four-character suffix unless the exact directory already exists. That
  is also what decides create-vs-update (`IS_EXISTING_PROJECT`).
- **The update path is much narrower than the create path.** For an existing
  project, template generation is skipped entirely so hand edits survive. Only
  the operator toggles, GPU tier, route exception, mesh join and cross-namespace
  policy sync are reapplied. Resource quota, limit ranges, Harbor settings,
  project users and robot accounts are written once at creation and are not
  reachable from the pipeline afterwards.

It no longer has a `validate_inputs`. What remains — `sanity_checks` — is the
half the schema cannot do, because it needs the repository on disk: does the
tenant directory exist, is the ArgoCD app name already taken, does the mesh this
namespace wants to join actually exist.

## `scaffold-mirror.sh`

Was `scaffold-registry-mirror.sh`, in a separate repository. It used to clone
customer-instances into `/tmp`, work there and push from there; it now runs in
that checkout, so every path is repo-relative like the other scripts.

Keeps one piece of its own validation: `validate_images` checks the
comma-separated image and tag lists element by element, which is a list-shape
rule the schema cannot express.

Reuses an existing registry entry when the endpoint URL is already registered
for the tenant, so a second image against the same registry does not create a
duplicate.

## `decommission.sh`

Handles `namespace.decommission` and `cso.decommission` via
`INPUT_DECOMMISSION_CSO`.

Moves the namespace's `values.yaml` into `.decommissioned_namespaces/` and
deletes the directory. When the last namespace goes, the whole tenant is moved
under `.decommissioned_tenants/` instead. Metadata entries move from
`active_*` to `decommissioned_*` with the request ticket and timestamps
attached, so the audit trail survives the deletion.

For an EgressIP object it also releases the IPs back to the cluster pool.

## `validate-mr-permissions.sh`

Was `validate-customer-values-file.sh`. Nothing to do with request payloads —
it runs on merge requests to `main` and fails if a prod namespace has a custom
Harbor robot account with `push`. This is the check that catches hand edits made
during MR review, which is precisely where the pipeline cannot see.

---

## Adding something

See [`../docs/extending.md`](../docs/extending.md). The short version: a new
field is a block in `request-schema.yaml` plus a use of its `INPUT_*` here.
`tools/check-schema-drift.sh` fails the pipeline if you do the second without
the first.
