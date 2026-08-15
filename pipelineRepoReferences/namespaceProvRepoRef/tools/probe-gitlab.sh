#!/bin/bash
# =============================================================================
# probe-gitlab.sh — answer the two questions about your GitLab that cannot be
# answered by reading code.
#
#   export GITLAB_HOST=https://gitlab.example.com
#   export GITLAB_TOKEN=glpat-...            # api scope
#   export GITLAB_PROJECT=dcs/dcs-customer-instances
#   ./tools/probe-gitlab.sh
#
# Nothing here creates a branch, a merge request or a namespace. Probe 1 only
# lints. Probe 2 does start a pipeline, and says so before it does.
#
# The same approach settled the 20-input question earlier: the documentation was
# ambiguous, one run on the real instance was not.
# =============================================================================
set -e

: "${GITLAB_HOST:?set GITLAB_HOST}"
: "${GITLAB_TOKEN:?set GITLAB_TOKEN}"
: "${GITLAB_PROJECT:?set GITLAB_PROJECT}"
REF="${GITLAB_REF:-main}"
PROJ=$(printf '%s' "$GITLAB_PROJECT" | sed 's|/|%2F|g')

api() { curl -sS -H "PRIVATE-TOKEN: ${GITLAB_TOKEN}" "$@"; }

echo "==========================================================================="
echo "  Probe 1 — how large may an input value be?"
echo "==========================================================================="
# Today's payloads are 600-900 bytes. They will grow: user lists, CVE
# allowlists, long comma-separated image lists. If 16 KB passes, the question is
# closed for good and REQUEST_PAYLOAD can stay a CI input. If it fails low,
# REQUEST_PAYLOAD moves to a CI variable (which has no such limit) and OPERATION
# stays an input -- a one-line change to .gitlab-ci.yml.
for SIZE in 1024 4096 16384 65536; do
    PAD=$(head -c "$SIZE" /dev/zero | tr '\0' 'x')
    BODY=$(printf '{"request_id":"REQ1","tenant_name":"probe","note":"%s"}' "$PAD")
    RESP=$(api --data-urlencode "content=$(cat <<YAML
spec:
  inputs:
    OPERATION: {default: "namespace.create"}
    REQUEST_PAYLOAD: {default: "{}"}
---
probe:
  script: [ "true" ]
  variables:
    P: \$[[ inputs.REQUEST_PAYLOAD ]]
YAML
)" "${GITLAB_HOST}/api/v4/projects/${PROJ}/ci/lint" \
        --data-urlencode "include_jobs=false" 2>/dev/null || true)
    VALID=$(printf '%s' "$RESP" | yq -p json -o json -r '.valid // "?"' 2>/dev/null || echo "?")
    printf "  payload %6d bytes -> lint valid=%s  (payload length %d)\n" "$SIZE" "$VALID" "${#BODY}"
done
echo
echo "  Note: lint only proves the config parses. The real test is Probe 2 with a"
echo "  large payload -- run it once by hand with a 16 KB REQUEST_PAYLOAD."
echo

echo "==========================================================================="
echo "  Probe 2 — can a browser on the Pages origin POST to the API?"
echo "==========================================================================="
echo "  This one cannot be answered by curl: it is about the browser's"
echo "  cross-origin rules, not the server's willingness. Do this instead:"
echo
echo "    1. open the deployed Pages site"
echo "    2. open the browser console"
echo "    3. paste:"
cat <<JS

       fetch('${GITLAB_HOST}/api/v4/projects/${PROJ//\%2F/%2F}/pipeline', {
         method: 'POST',
         headers: { 'PRIVATE-TOKEN': '<your token>', 'Content-Type': 'application/json' },
         body: JSON.stringify({ ref: '${REF}', inputs: {
           OPERATION: 'namespace.create',
           REQUEST_PAYLOAD: '{"request_id":"PROBE"}'
         }})
       }).then(r => r.json()).then(console.log).catch(console.error);

JS
echo "  A CORS error in the console means the direct-trigger button cannot work,"
echo "  and the form falls back to Copy — which is already built and needs no"
echo "  change. Anything else (including a 400 about the payload) means the"
echo "  browser was allowed through and the button is viable."
echo
echo "  It will start a real pipeline if it succeeds, so use a throwaway REQUEST_ID"
echo "  and cancel the run."
echo

echo "==========================================================================="
echo "  Probe 3 — does this GitLab accept 'inputs' on the pipeline API at all?"
echo "==========================================================================="
echo "  (Older GitLab only accepts 'variables' here. Read-only check:)"
api "${GITLAB_HOST}/api/v4/version" | yq -p json -o json -r '"  GitLab " + .version' 2>/dev/null || echo "  could not read version"
