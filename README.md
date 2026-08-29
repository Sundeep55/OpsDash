# OpsDash — Ops Control Plane

A read-only dashboard over the GitOps customer-instances repository. It walks the
repo, builds a queryable picture of the estate — clusters, tenants, namespaces,
capsules, users, siglums, tickets — and serves it as a Vue SPA plus a stable
"API as a product" for other teams.

It reads. The one exception is pipeline triggering, which asks GitLab to start an
onboarding pipeline and is off by default; see [Pipeline
triggering](#pipeline-triggering).

---

## Configuration in one sentence

**Everything is an environment variable read in `ops_portal/settings.py` (or
`dashboard/pipeline/config.py`), and in Kubernetes every non-secret one comes
from the ConfigMap and every secret from the Secret — both rendered by
`deploy/opsdash`.** Nothing is configured in code.

| Where | What | File |
|---|---|---|
| Local | environment variables | your shell, or `.claude/launch.json` for the dev server |
| Kubernetes — non-secret | `ops-portal-config` ConfigMap | `deploy/opsdash/values.yaml` → `templates/configmap.yaml` |
| Kubernetes — secret | `ops-portal-secret` Secret | created out of band, **not** by the chart |

If a setting is not in the tables below, it does not exist. An env var the code
never reads is worse than no setting at all — see the note on `PORTAL_NAME` under
[What changed](#what-changed).

---

## Settings reference

### Django

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `True` | `values.yaml` → `django.debug`. The chart warns on install if true. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Derived from `hostname` by the chart. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://localhost,...` | Derived from `hostname` by the chart. |
| `DATABASE_PATH` | `<repo>/db.sqlite3` | Must sit under `persistence.mountPath`; the chart fails the render otherwise. |
| `PORTAL_NAME` | `Ops Control Plane` | Header title. |
| `PORTAL_TITLE` | `IDP Dashboard` | Browser tab title. |
| **`DJANGO_SECRET_KEY`** | insecure built-in | **Secret.** Without it production runs on the key committed in `settings.py`. |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | — | **Secret**, optional. `entrypoint.sh` creates the user on first start if the first two are set. |

### GitLab sync — the repo the dashboard reads

| Variable | Default | Notes |
|---|---|---|
| `GITLAB_URL` | — | |
| `GITLAB_PROJECT_ID` | — | The **customer-instances** repo. |
| `GITLAB_BRANCH` | `main` | |
| `GITLAB_SSL_VERIFY` | `true` | |
| `POLL_INTERVAL_SECONDS` | `60` | Also derives the sidecar's liveness staleness limit (6×, floor 300s). |
| `GIT_BROWSER_URL` | empty | Deep links from the UI into the repo tree. Empty hides "View in Git". |
| **`GITLAB_TOKEN`** | — | **Secret.** Read-only `api` scope is enough. |

With any of URL / project / token unset the sync falls back to a local directory
(`--repo-path`), which is what makes local development work with no GitLab.

### GitOps layout — names the sync matches on

Only set these when the real repo names a block or file differently from the
defaults. Setting one in the ConfigMap means a rename in the GitOps repo does not
need an image rebuild.

| Variable | Default |
|---|---|
| `GITOPS_PROVISIONER_KEY` | `namespace-provisioner` |
| `GITOPS_CAPSULE_KEY` | `tenant-provisioner` |
| `GITOPS_EGRESS_KEY` | `egress` |
| `GITOPS_SERVICE_MESH_KEY` | `service-mesh` |
| `GITOPS_REGISTRY_CONFIG_KEY` | `registry-config` |
| `GITOPS_TENANT_METADATA_FILE` | `tenant-metadata.yaml` |
| `GITOPS_CHART_FILE` | `Chart.yaml` |
| `GITOPS_TEMPLATES_DIR` | `templates` |
| `GITOPS_DECOMMISSIONED_TENANTS_DIR` | `.decommissioned_tenants` |
| `GITOPS_DECOMMISSIONED_NAMESPACES_DIR` | `.decommissioned_namespaces` |
| `GITOPS_SKIP_FILENAMES` | `egressip-pool.yaml` |

In the chart these live under `gitopsLayout:` as camelCase keys, and only the
ones you set are emitted — anything omitted keeps the `settings.py` default.

### Pipeline triggering

| Variable | Default | Notes |
|---|---|---|
| `PIPELINE_ENABLED` | `false` | **The on/off switch.** False means no trigger control renders anywhere. |
| `PIPELINE_PROJECT_ID` | — | The **namespace-provisioner** repo — the one owning `.gitlab-ci.yml` and `request-schema.yaml`. *Not* `GITLAB_PROJECT_ID`. |
| `PIPELINE_GITLAB_URL` | falls back to `GITLAB_URL` | |
| `PIPELINE_REF` | `main` | Branch the pipeline runs on. |
| `PIPELINE_SCHEMA_PATH` | `request-schema.yaml` | Path within that project. |
| `PIPELINE_SCHEMA_TTL_SECONDS` | `300` | How long a fetched schema is reused. |
| `PIPELINE_SSL_VERIFY` | falls back to `GITLAB_SSL_VERIFY` | |
| `PIPELINE_ALLOWED_GROUP` | empty | Restrict triggering to one Django group. Empty means any signed-in user. |
| **`PIPELINE_TOKEN`** | — | **Secret.** `api` scope on the pipeline project. |
| `PIPELINE_SCHEMA_FILE` | — | **Local only, not in the chart.** See [dry run](#dry-run-no-gitlab). |

### Not chart-managed

`SIDECAR_HEARTBEAT_PATH` (default `/tmp/sidecar-heartbeat`) is read by the sync
sidecar and its health probe. Set it through `extraEnv` in `values.yaml` if you
ever need to.

---

## What changed

Recent work, and the switch that controls each piece.

### Capsules are a first-class entity

A capsule is a delegated slice of a tenant whose users create their own
namespaces against one shared quota. The estate deliberately does not track those
namespaces — only the capsule and its quota.

- Parsed from the `tenant-provisioner` block (`GITOPS_CAPSULE_KEY`), which is the
  only thing distinguishing a capsule directory from a namespace one.
- Own tab, list and detail page; counted separately in the global KPIs and in
  per-cluster telemetry, at every lifecycle.
- Threaded through **Users**, **Siglums** and **Requests**. Capsule membership
  used to live in JSON columns no query could reach, so someone owning three
  capsules and no namespaces appeared to have no access at all. `UserAccess` now
  points at a namespace *or* a capsule (migration `0008`).
- No switch. Capsules appear when the repo contains them.

### Pipeline triggering — `PIPELINE_ENABLED`

Context-aware buttons that start an onboarding pipeline: New Tenant, New
Namespace, New Capsule, Add to a tenant, Request Change on a namespace or
capsule. The form is generated from `request-schema.yaml`, fetched live from the
pipeline project — a field merged into the schema appears here with no OpsDash
release.

- Off by default. Every control is hidden unless the backend reports triggering
  configured *and* permitted for that user.
- The rule engine is vendored byte-identical from the pipeline repo
  (`static/js/vendor/schema-form.js`) so the browser and the CI shim cannot
  disagree about what a valid request is. `tools/check_schema_form_drift.py`
  enforces that.
- Pipelines run as one service token, so each request carries a `TRIGGERED_BY`
  input naming the signed-in user. That is **not** the payload's
  `requester_email`, which is the customer who raised the ITSM ticket.
- Restrict who may use it with `PIPELINE_ALLOWED_GROUP`.

### CSV exports

Tenants, namespaces, capsules and siglums, each as "everything on screen" or one
record. Directory exports carry the current search, cluster and status filters.
Columns are the project-management view — owner, placement, lifecycle, reserved
CPU and memory, ticket. Operators, robot accounts, network policy and route
exceptions are deliberately excluded.

Resource columns are what Git **reserves**, not measured usage; the column names
say so (`cpu_requested_cores`, `memory_requested_gb`) because a spreadsheet
outlives the page it came from. No switch.

### Route exception expiry

A route exception is a time-limited waiver. Two fixes worth knowing:

- `days_active` is capped at the expiry date. It used to be `today - granted_at`
  with no ceiling, so a grant that ran its 90 days and lapsed in March reported
  "200 days active" in September.
- The banner shows everything expiring plus lapses from the last
  **14 days** (`RouteException.EXPIRED_NOTICE_DAYS`). The record is never edited
  or removed to quiet it — that would be tampering with the audit trail — and the
  Security tab still lists every one. Only the alerting is bounded. Rows are
  clickable through to the namespace.

Not env-configurable: the windows are constants on the model, next to the
reasoning.

### Deployment as a Helm chart

`deploy/opsdash` replaces the old flat `manifest.yaml`. Same five objects with
the same names, so ArgoCD adopts what is already in the cluster. See
[deploy/opsdash/README.md](deploy/opsdash/README.md) — it records four things
that were wrong in the manifest, including a referenced Secret that nothing
created.

### `PORTAL_NAME` / `PORTAL_TITLE` now actually work

Both were set in the ConfigMap and hardcoded in `settings.py`, so setting them
changed nothing and gave no indication why. They read from the environment now.

---

## Running it

### Against GitLab

```bash
export GITLAB_URL=https://gitlab.example.com GITLAB_PROJECT_ID=1234 GITLAB_TOKEN=…
python manage.py migrate
python manage.py sync_gitops
python manage.py runserver
```

### Against local files

The sync falls back to `--repo-path` whenever the GitLab variables are not all
set, which an ordinary development shell already satisfies.

```bash
python manage.py sync_gitops --repo-path /path/to/customer-instances
```

`tools/demo_estate.py` generates a synthetic estate at production scale for
exercising the UI. See [tools/README.md](tools/README.md).

### Dry run — no GitLab

`PIPELINE_SCHEMA_FILE` points the trigger form at a schema on disk and prints
requests to the console instead of sending them. There is no code path from that
mode to the network.

```bash
PIPELINE_ENABLED=true PIPELINE_SCHEMA_FILE=/path/to/request-schema.yaml \
  python manage.py runserver
```

---

## Build gates

Four checks run in the Docker build, each turning a silent runtime failure into a
build failure:

```bash
python3 tools/check_py39_compat.py        # syntax the 3.9 dev boxes cannot run
python3 tools/check_templates.py          # Vue placement + multi-line {# #} comments
python manage.py build_css --check        # a class the stylesheet lacks
python3 tools/check_schema_form_drift.py  # vendored rule engine vs the pipeline's
```

One more is worth running before you commit, though the image build cannot:

```bash
python manage.py makemigrations --check --dry-run   # a model change with no migration
```

`build_css` deserves a note: `static/css/tailwind.css` is a vendored artifact, so
any class added afterwards — especially inside a JS template string, which
Tailwind's scanner never sees — silently resolves to nothing and the element
renders unstyled. The command rebuilds the missing rules from the design tokens
already in that file and **reports anything it cannot express rather than
skipping it**.

---

## Layout

```
dashboard/
  gitops/          the repo walk: fetcher, walker, parsers, reconciler
  api/internal/    endpoints for the SPA          (/api/v2/…)
  api/product/     the stable contract for others (/api/v2/…)
  pipeline/        trigger config, schema fetch, the POST to GitLab
  templates/       Django templates hosting the Vue app
static/js/
  app.js           composition only
  composables/     state and data access
  components/      reusable markup
  lib/             HTTP and helpers
  vendor/          the request-schema rule engine, shared with the pipeline repo
deploy/opsdash/    the Helm chart
tools/             fixtures, the demo estate, and the build gates
```

`pipelineRepoReferences/` is a **reference copy** of the onboarding pipeline
repository, kept here so the schema and rule engine can be compared against it.
It is not deployed and changes made there must be copied to the real repo.
