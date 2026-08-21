# Customer onboarding

Namespaces, DevSpaces, EgressIP objects and registry mirrors, requested through
a form and provisioned by a pipeline that opens a merge request.

- **[docs/extending.md](docs/extending.md)** — adding a field, an option or an operation
- **[pipeline-scripts/README.md](pipeline-scripts/README.md)** — what each script does
- **[pages/README.md](pages/README.md)** — the form, scale figures, how the trigger works

---

## Before anyone uses the form

Five steps. Two are one-time project settings, one is per-operator, and two are
just verification — **there are no new CI/CD variables to create.**

### 1. Merge to `main`

The `pages` job runs on a merge and publishes the site. It does not run on
form-triggered pipelines: the inventory only moves when a branch is merged, so
that is the only thing that rebuilds it.

Find the URL under **Deploy → Pages**.

### 2. Turn on Pages access control

**Settings → General → Visibility → Pages → "Only project members".**

Do this before sharing the link. The published `index.json` lists every tenant
and namespace along with each tenant's requester address and cost centre.
Nothing there is secret — any project member can already read it from the
repository — but it is concentrated into one file that a URL alone would
otherwise hand out.

### 3. Check the variables that already existed

These are the same ones the old pipelines used. **Settings → CI/CD → Variables.**
If provisioning worked before this change, they are already set and there is
nothing to do.

| Variable | What it is |
|---|---|
| `GITLAB_TOKEN` | The token the scripts push the scaffold branch with. Masked. |
| `HARBOR_URL` | Registry the `pipeline-tools` job image is pulled from. |
| `HARBOR_LOCAL_URL` | Written into each generated `Chart.yaml` as the OCI repository host. |
| `HARBOR_OCI_PROJECT` | The OCI project within it. |

Optional, all with working defaults — set only to override:
`DEBUG` (`true` turns on `set -x`), `REGISTRY_CONFIG_CHART_VERSION`,
and the `ROBOT_ACCOUNT_ENV*` names used by internal registry replication.

### 4. Nothing to set for the form's own configuration

The form needs to know which GitLab, which project and which branch. It gets all
three from **GitLab's predefined variables**, which every job has automatically:

| Used | Predefined as |
|---|---|
| GitLab URL | `CI_SERVER_URL` |
| Project | `CI_PROJECT_ID`, `CI_PROJECT_PATH` |
| Branch | `CI_DEFAULT_BRANCH` |

`tools/build-pages.sh` writes them into `config.json` at build time, so the form
shows *"Requests go to … on … , branch …"* and never asks. **Do not create
variables with these names** — GitLab supplies them, and overriding them would
point the form somewhere else.

A CI/CD variable is deliberately *not* used for the API token. A static page
cannot read CI variables at all — they exist only inside a running job — and
baking one into the published site would turn it into a file anyone who can load
the page can read. See [pages/README.md](pages/README.md) for the three ways to
authenticate and what each costs.

### 5. Each operator: a personal access token

Only needed for the **Trigger pipeline** button. **Copy request JSON** works with
no token at all, so this step is optional per person.

1. **User settings → Access tokens → Add new token**
2. Scope: **`api`**. Nothing else.
3. Expiry: short. It is re-entered in a minute.
4. The person needs at least the **Developer** role on this project.
5. Open the form → **Trigger settings** → paste it → **Save**.

It is stored in that operator's own browser and sent only to your GitLab. The
pipeline then runs *as them*, so "triggered by" names a person and their own
permissions apply — someone without project access cannot trigger anything,
whatever the form lets them type.

On a shared workstation profile the token stays for whoever uses the browser
next; there is a **Clear token** button for that.

---

## Using it

1. Open the Pages URL.
2. Pick the operation. Only that operation's fields are shown — a registry
   mirror never mentions GPUs, a decommission asks six questions.
3. Fill it in. Tenant and namespace are picklists drawn from the repository, so
   nothing has to be written down beforehand, and the form says whether the
   tenant already exists.
4. **Trigger pipeline**, or **Copy request JSON** and paste it into
   *Build → Pipelines → Run pipeline* as `REQUEST_PAYLOAD` with `OPERATION`
   set alongside.
5. The pipeline pushes a branch. **Review and merge the merge request** — that
   step is unchanged and still where a human approves the change.

## Without the form

The pipeline takes two inputs and nothing else, so the Run-pipeline page remains
a complete fallback if Pages is ever down:

- `OPERATION` — one of the seven in the dropdown
- `REQUEST_PAYLOAD` — the request as JSON

`request-schema.yaml` lists the fields each operation accepts.

## When something looks wrong

| Symptom | Where to look |
|---|---|
| "Could not read any fields from request-schema.yaml" | [pipeline-scripts/README.md](pipeline-scripts/README.md#if-it-says-it-cannot-read-the-schema) |
| Form shows empty tenant/namespace lists | The `pages` job has not run since the tenant was merged. The footer shows the commit it was built from. |
| Trigger button reports a cross-origin error | Your GitLab does not allow browser API calls from the Pages origin. Use Copy; see `tools/probe-gitlab.sh`. |
| A request was rejected for a field the operator did fill in | `tools/cases.json` plus `./tools/test-cases.sh` reproduces validation locally. |
