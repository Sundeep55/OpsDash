"""Triggering the onboarding pipeline from the dashboard.

OpsDash reads the GitOps repository and shows what is in it. This package is the
one place it writes anywhere -- and even here it writes nothing itself: it asks
GitLab to start a pipeline, and the pipeline does the work. Nothing in this
package touches the local database or the repository.

That distinction is the whole design. The GitLab Pages form remains the primary
route and works with OpsDash switched off entirely; this is a shortcut for
someone already looking at the tenant they want to change, not a dependency.

Three modules:

    config    where to send a request, and whether the feature is on at all
    schema    request-schema.yaml, fetched from the pipeline repo and cached
    trigger   the boundary checks, and the POST to GitLab

The rules that decide whether a *request* is valid deliberately do not live
here. request-schema.yaml declares them once; the browser applies them so the
operator finds out while typing, and pipeline-scripts/load-payload.sh enforces
them as the actual gate. A third copy in Python would be a third thing to drift.
What this package checks is narrower and different in kind -- see the note in
trigger.py.
"""
