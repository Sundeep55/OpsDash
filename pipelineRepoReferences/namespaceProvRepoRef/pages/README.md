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

## Running it locally

```bash
./tools/build-pages.sh /tmp/site && cp tools/cases.json /tmp/site/
python3 -m http.server 8765 --directory /tmp/site
```

Then `http://localhost:8765` for the form and `/parity.html` for the engine
check. `REPO_ROOT=/path/to/fixture` points the index at a fake tenant tree.
