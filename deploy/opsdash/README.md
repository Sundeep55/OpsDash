# opsdash

The Ops Control Plane deployment, as a Helm chart. Replaces the flat
`manifest.yaml` that used to live at the repository root.

The default render produces the same five objects, with the same names, as that
manifest did — `ops-portal`, `ops-portal-config`, `ops-portal-data`,
`ops-portal-svc`, `ops-portal-route`. That is deliberate: ArgoCD adopts the
objects already in the cluster instead of creating a parallel set.

---

## Install

```bash
helm upgrade --install ops-portal deploy/opsdash \
  --namespace dcs-cluster-config --create-namespace \
  --set hostname=ops-control-plane.example.com \
  --set gitlab.projectId=1234 \
  --set image.tag=0.1.0
```

The chart does not hardcode a namespace, unlike the old manifest. Pass
`--namespace`, or let ArgoCD's `destination.namespace` place it.

### The Secret comes first

Both containers mount `ops-portal-secret` and will not start without it. The
chart does not create it — see *What changed* below.

```bash
oc create secret generic ops-portal-secret \
  --namespace dcs-cluster-config \
  --from-literal=DJANGO_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(50))')" \
  --from-literal=GITLAB_TOKEN='<read-only api token>'
```

| Key | Required | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | yes in production | Without it Django falls back to the insecure key committed in `settings.py`. |
| `GITLAB_TOKEN` | yes | Read-only `api` scope. Without it every poll fails and the dashboard stays empty. |
| `PIPELINE_TOKEN` | only with `pipeline.enabled` | Reads the schema from the *pipeline* project; `read_api` is enough. Pipelines are started with the operator's own token, not this one. |
| `DJANGO_SUPERUSER_USERNAME` | no | `entrypoint.sh` creates the user on first start if this and the password are set. |
| `DJANGO_SUPERUSER_PASSWORD` | no | |
| `DJANGO_SUPERUSER_EMAIL` | no | |

For a throwaway local install only, `--set secret.create=true --set
secret.stringData.GITLAB_TOKEN=…` renders it from values instead. Never with
ArgoCD: values are in Git.

---

## ArgoCD

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ops-portal
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://gitlab.com/dcs/ops-control-plane.git
    targetRevision: main
    path: deploy/opsdash
    helm:
      valueFiles:
        - values.yaml
      parameters:
        - name: hostname
          value: ops-control-plane.example.com
        - name: gitlab.projectId
          value: "1234"
  destination:
    server: https://kubernetes.default.svc
    namespace: dcs-cluster-config
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

Two things to know before turning `selfHeal` on:

- **`prune: true` will not take the database.** The PVC carries
  `helm.sh/resource-policy: keep`, and ArgoCD honours it.
- **The Secret must stay outside this Application**, or `selfHeal` will try to
  reconcile an object that is not in Git and report the app permanently
  OutOfSync.

---

## Values worth knowing

`hostname` is the one that matters. It sets four things that all have to agree —
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, the Route host, and the
`Host:` header on every HTTP probe. The kubelet would otherwise probe by pod IP,
which is not in `ALLOWED_HOSTS`, so Django answers `400 DisallowedHost` and the
container never leaves `CrashLoopBackOff`. Override the derived values
individually only if the Route hostname genuinely differs from what Django
should accept.

| Value | Default | |
|---|---|---|
| `hostname` | `ops-control-plane.com` | Required. See above. |
| `image.repository` / `image.tag` | `registry.com/images/ops-control-plane` / *appVersion* | |
| `gitlab.projectId` | `"xx"` | Placeholder. The install warns if left as-is. |
| `gitlab.pollIntervalSeconds` | `30` | Also derives the sidecar's liveness staleness limit (6×, floor 300s). |
| `gitopsLayout` | `{}` | Only the keys you set are emitted; the rest keep the `settings.py` defaults. Lets a rename in the GitOps repo skip an image rebuild. |
| `persistence.retain` | `true` | Keeps the PVC on uninstall. |
| `route.enabled` | `true` | OpenShift. Swap for `ingress.enabled` on plain Kubernetes. |
| `secret.create` | `false` | See above. |

### Pipeline triggering

Off by default. When on, operators can start an onboarding pipeline from the
tenant, namespace or capsule they are already looking at, instead of retyping
its name into the GitLab form.

```bash
--set pipeline.enabled=true \
--set pipeline.projectId=77          # the project that owns the pipeline
```

`pipeline.projectId` is **not** `gitlab.projectId`. The latter is the
customer-instances repo the dashboard reads; this is the repo that owns
`.gitlab-ci.yml` and `request-schema.yaml`. Enabling the feature without it
fails the render rather than producing a dashboard whose buttons all error.

The form is generated from `request-schema.yaml`, fetched live from that project
and cached for `pipeline.schemaTtlSeconds`. A field merged into the schema
therefore appears in the dashboard with no OpsDash release.

Three things worth knowing:

- **It is a shortcut, not a dependency.** If the pipeline project is
  unreachable, or the feature is off, the dashboard shows no trigger controls
  and behaves exactly as it did before. The GitLab Pages form is unaffected
  either way, and remains the route that works when OpsDash is down.
- **Two tokens, and only one of them is yours to configure.** `PIPELINE_TOKEN`
  reads `request-schema.yaml` and nothing else, so `read_api` on the pipeline
  project is enough. Pipelines are started with the operator's own GitLab token,
  which they supply in the form and which never reaches the server's storage —
  so GitLab records each pipeline against the person who asked for it, and the
  CI file needs no attribution input.
- **Who may trigger.** By default, anyone who can sign in — the same scope as
  the rest of the dashboard, where everyone can already read everything. Set
  `pipeline.allowedGroup` to restrict it to members of one Django group.

`replicas` is not a value. One Gunicorn process and one sync daemon share one
SQLite file on a ReadWriteOnce volume; a second replica cannot schedule anyway,
because the volume is already attached.

---

## What changed from `manifest.yaml`

Four things were wrong in a way that only shows up in the cluster, so they were
fixed rather than transcribed.

**The Secret never existed.** Section 2 of the manifest was a heading and a
blank line, but both containers had `secretRef: {name: ops-portal-secret}`. A
referenced Secret that does not exist leaves the pod in
`CreateContainerConfigError` — that manifest could not have started from a clean
namespace. The chart keeps the reference required (`secret.optional: false`) on
purpose: Django silently falling back to its built-in insecure `SECRET_KEY` in
production is worse than a pod that refuses to start.

**`strategy: Recreate`.** The manifest took Kubernetes' default RollingUpdate.
With `maxSurge` rounding up to 1, that starts the replacement pod before
terminating the old one — and the replacement wants the same ReadWriteOnce
volume the old pod still holds. If the scheduler picks a different node it
cannot attach, and the old pod is never terminated because the new one never
goes Ready. The rollout wedges until it times out. Whether it happens at all
depends on node placement, so it works until it doesn't.

**The Route had no `host`.** It would have taken a router-generated hostname,
which is then not in `ALLOWED_HOSTS` — a 400 on every request through the URL
the router just advertised.

**Config changes did nothing.** `envFrom` is read once at container start, so
editing the ConfigMap had no effect until something happened to restart the pod.
The pod template now carries a `checksum/config` annotation, so a ConfigMap
change rolls the pods.

Two smaller ones: the hostname was written out four times independently, and is
now derived once; and `PORTAL_NAME` / `PORTAL_TITLE` were set in the ConfigMap
but hardcoded in `settings.py`, so setting them changed nothing — `settings.py`
now reads them from the environment.

The manifest's comment claiming the startup probe covers `collectstatic` was
also stale: the Dockerfile bakes static files in at build time, and
`entrypoint.sh` only runs `migrate`. The startup budget is for migrations.

### Not in this chart

`rbac.yaml` at the repository root is cluster configuration — tenant
ClusterRoles and Kyverno guardrails. It is not part of deploying this
application and is not templated here.
