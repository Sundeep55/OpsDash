# `pages/` — the onboarding form

A static site served from GitLab Pages. Four files, no build step, no npm, no
CDN: it has to serve in an airgapped environment, and a form does not need a
framework.

| File | What it is |
|---|---|
| `index.html` | The page. Three steps: pick an operation, fill it in, send it. |
| `style.css` | Hand-written. Follows the browser's light/dark preference. |
| `schema-form.js` | **The rules.** Resolution, `show_if`, validation, payload building. No DOM in it. |
| `app.js` | DOM wiring and the GitLab call. No rules in it. |
| `parity.html` | Runs `tools/cases.json` through `schema-form.js`. |

## It renders itself

Nothing here knows what a siglum is. The form is built at page load from
`schema.json` — `request-schema.yaml`, converted by `tools/build-pages.sh` — so
a field added to the schema appears on the form with no change to any file in
this directory. Groups become sections, `show_if` decides what is on screen,
`options` becomes a dropdown, `source` becomes a picklist.

That is the whole point: adding a capability should touch the schema and the
scaffold script, and nothing else.

## Why the rules are in their own file

`schema-form.js` has no DOM references and no dependencies, because two things
load it: this form, and later OpsDash. They must agree with each other and with
`pipeline-scripts/load-payload.sh`.

**The shim is the gate.** Nothing in a browser can be a security control — a
request can be posted straight to the API. `schema-form.js` exists so an
operator finds out about a mistake while typing rather than from a red pipeline
five minutes later. `tools/cases.json` is run through both engines and they
must reach the same verdict on every case; `tools/test-cases.sh` does the shell
half in CI, `parity.html` does the browser half.

One case file, not two. There used to be two, and merging them immediately
exposed three rules the browser was silently letting through.

## The index

`build-pages.sh` also emits `index.json`: every cluster, tenant and namespace in
the repository, plus each tenant's siglum, cost centre and requester.

This is what stops operators writing names down before triggering a pipeline.
Choose a cluster and the tenant list narrows; choose a tenant and the namespace
list narrows. The form also says plainly whether the tenant already exists, so
create-versus-update is answered before submitting rather than by a failed run —
and *"You cannot leave the Project Name empty/default for an existing tenant"*
becomes unreachable, because an existing tenant never renders an empty namespace
field.

It is as fresh as the last merge to `main`, which is when namespaces actually
come into existence. The footer shows the commit and time so nobody has to
guess.

## Sending the request

**Copy request JSON** always works, needs nothing configured, and cannot break:
paste into *Build → Pipelines → Run pipeline* as `REQUEST_PAYLOAD` and set
`OPERATION` beside it.

**Trigger pipeline** posts to the API with a personal access token the operator
saves in their own browser. The pipeline then runs as them, so the audit trail
names a person rather than a shared token. Whether the browser is allowed to
make that cross-origin call depends on the GitLab instance —
`tools/probe-gitlab.sh` explains how to find out. If it is refused the button
reports it and Copy is unaffected; the form is fully usable either way.

A trigger token embedded in this page was the third option and is not used: it
would be readable by anyone who can load the site, and the audit trail would
name the token instead of the person.

## Scale, size and who can use it

Measured against a fixture of **200 tenants / 804 namespaces**, which is the
shape of the real repository:

| | |
|---|---|
| `index.json` | 52 KB |
| Tenant picklist | 200 entries, one `<datalist>` |
| Namespace picklist | only that tenant's namespaces (2–6), never all 804 |
| Re-render per keystroke | ~1.5 ms |
| Pages build | ~13 s, and only on a merge to main |

The namespace list is scoped by the chosen tenant, so it never grows with the
estate. The tenant list is a `<datalist>`, which is a native type-ahead rather
than a 200-row dropdown: the operator types a few characters and the browser
filters. Nothing here needs virtualising.

**Payload size.** The whole request travels as one CI input value, so the form
shows its byte count next to the payload preview.

| Operation | Worst case |
|---|---|
| namespace.create | 743 B |
| mirror.create | 587 B, **+ ~40 B per extra image** |
| everything else | under 520 B |

Only a registry mirror grows, because the image list is comma-separated and
unbounded: 100 images is about 3.6 KB. The count turns red above 8 KB as an
early warning; nothing in normal use approaches it.

**Multiple users.** The site is static, so any number of people can use it at
once. Each operator's token lives in their own browser; nothing is shared.

## Why the token cannot come from a CI/CD variable

A natural request is "read the API key from a project or group variable so it is
the same for everyone". **A static page cannot do that.** CI/CD variables exist
only inside a running job's environment. Pages serves files; there is no runtime
to read them from, and no API that hands them out without already having a
credential.

The only way to get one into the page is for the `pages` job to write it into a
file at build time — and then it is not a variable any more, it is a published
static asset that anyone who can load the site can read out of the JavaScript.

So the *configuration* and the *secret* are treated differently:

- **Configuration is baked.** `build-pages.sh` writes `config.json` from
  GitLab's own predefined variables (`CI_SERVER_URL`, `CI_PROJECT_ID`,
  `CI_PROJECT_PATH`, `CI_DEFAULT_BRANCH`). None are secrets, and the operator is
  never asked for them. The form shows where requests will go and moves on.
- **The secret is not.** The only thing left in Trigger settings is the token.

### The three ways to authenticate, and what each costs

| | Operator setup | Audit trail | Secret in the page |
|---|---|---|---|
| **Personal access token** (today) | Mint once, paste once | Names the person | none |
| **OAuth application (PKCE)** | none | Names the person | none — PKCE is designed for public clients |
| **Baked trigger token** | none | Names the token | yes |

**OAuth is the answer to "no configuration at all".** An admin registers one
GitLab OAuth application whose redirect URI is the Pages URL; the application id
is public by design and there is no client secret in the PKCE flow. The operator
clicks Trigger, is bounced to GitLab (usually already logged in), and comes back
authenticated. No token is ever typed or stored, and the pipeline still runs as
them.

**A baked trigger token is a legitimate choice, with eyes open.** Its blast
radius is smaller than it first sounds — a trigger token can only start
pipelines on this project; it cannot read code, write anything, or reach another
project. With Pages access control on, the people who can read it are people who
could already start a pipeline from the GitLab UI. What it costs is the audit
trail: every run shows as the token rather than the person. The request payload
still carries `request_id` and `requester_email`, and the merge request still
needs a named human to approve it, so accountability is not lost entirely — but
"who triggered this" stops being answerable.

It is deliberately **not** implemented. Adding it is a few lines in
`build-pages.sh`; it is left out so that nobody enables it without deciding to.

## Running it locally

```bash
./tools/build-pages.sh /tmp/site && cp tools/cases.json /tmp/site/
python3 -m http.server 8765 --directory /tmp/site
```

Then `http://localhost:8765` for the form and `/parity.html` for the engine
check. `REPO_ROOT=/path/to/fixture` points the index at a fake tenant tree.
