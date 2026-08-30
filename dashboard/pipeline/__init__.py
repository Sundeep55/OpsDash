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

TWO TOKENS, DELIBERATELY
------------------------
PIPELINE_TOKEN is a service credential and reads one thing: the schema. It is
configuration, it lives in the Secret, and the browser never sees it.

Starting a pipeline uses the operator's own GitLab token, sent with their
request and used for that one call. It is never written down -- not to the
database, not to the Django session, not to a log line -- and the browser holds
it in sessionStorage, so it is gone when the tab closes.

That split is what keeps the CI contract at the two inputs it always had. A
shared service token would make every pipeline in GitLab look like the same bot,
which is why an earlier version carried a third input, TRIGGERED_BY, to say who
had really asked. Sending the request as the operator makes GitLab's own record
correct, so nothing has to be carried alongside it.

The rules that decide whether a *request* is valid deliberately do not live
here. request-schema.yaml declares them once; the browser applies them so the
operator finds out while typing, and pipeline-scripts/load-payload.sh enforces
them as the actual gate. A third copy in Python would be a third thing to drift.
What this package checks is narrower and different in kind -- see the note in
trigger.py.
"""
