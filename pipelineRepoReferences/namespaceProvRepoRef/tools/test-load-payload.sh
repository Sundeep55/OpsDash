#!/bin/bash
# =============================================================================
# test-load-payload.sh — the shim is the validation gate, so it gets a test.
#
# Collapsing 25 CI inputs into one JSON string removed GitLab's server-side
# enforcement of types and option lists. load-payload.sh puts that back. If it
# is wrong, a typo'd target cluster that GitLab would have rejected reaches
# `mkdir -p` and quietly creates a new top-level cluster directory. So every
# rule it enforces is asserted here.
#
#   ./tools/test-load-payload.sh
#
# Runs the real script against the real schema in a subshell per case. Needs yq
# and nothing else.
# =============================================================================

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
export REQUEST_SCHEMA="${ROOT}/request-schema.yaml"
SHIM="${ROOT}/pipeline-scripts/load-payload.sh"

PASS=0
FAIL=0

# Run the shim in a subshell. Prints its output; returns its exit status.
run_case() {
    ( export OPERATION="$1" REQUEST_PAYLOAD="$2"
      # shellcheck disable=SC1090
      source "$SHIM" >/dev/null 2>&1
      # Emit what the scripts would see, for the assertions below.
      env | grep '^INPUT_' | sort
    ) 2>/dev/null
}

run_case_verbose() {
    ( export OPERATION="$1" REQUEST_PAYLOAD="$2"
      source "$SHIM" 2>&1
    )
}

ok()   { PASS=$((PASS+1)); printf "  ok    %s\n" "$1"; }
bad()  { FAIL=$((FAIL+1)); printf "  FAIL  %s\n" "$1"; [ -n "$2" ] && printf "        %s\n" "$2"; }

# Expect the shim to accept the payload.
accepts() {
    local desc="$1" op="$2" payload="$3"
    if run_case "$op" "$payload" >/dev/null; then ok "$desc"
    else bad "$desc" "expected accept, got reject: $(run_case_verbose "$op" "$payload" | grep '^ERROR' | head -1)"; fi
}

# Expect the shim to reject, and the message to mention $4.
rejects() {
    local desc="$1" op="$2" payload="$3" want="$4" out
    out=$(run_case_verbose "$op" "$payload" 2>&1)
    if printf '%s' "$out" | grep -q '^ERROR'; then
        if [ -z "$want" ] || printf '%s' "$out" | grep -qi -- "$want"; then ok "$desc"
        else bad "$desc" "rejected, but not for '$want': $(printf '%s' "$out" | grep '^ERROR' | head -1)"; fi
    else
        bad "$desc" "expected reject, was accepted"
    fi
}

# Expect INPUT_<name> to come out as <value>.
exports() {
    local desc="$1" op="$2" payload="$3" var="$4" want="$5" got
    got=$(run_case "$op" "$payload" | grep "^${var}=" | head -1 | cut -d= -f2-)
    if [ "$got" = "$want" ]; then ok "$desc"
    else bad "$desc" "$var: expected '$want', got '$got'"; fi
}

# --- fixtures ----------------------------------------------------------------
BASE='"request_id":"REQ0001","requester_email":"a.b@zzz.com","requested_at":"01/04/2026 13:47:48","target_cluster":"qa-w1","tenant_name":"acme","siglum":"TD01","cost_center":"XX/YY1234-56789","lifecycle":"dev"'
NS_MIN="{$BASE}"

echo "==========================================================================="
echo "                        load-payload.sh test suite                         "
echo "==========================================================================="

echo ""
echo "-- happy paths"
accepts "minimal namespace.create"                  namespace.create "$NS_MIN"
accepts "cost centre may be explicitly empty"       namespace.create "{$BASE,\"cost_center\":\"\"}"
accepts "prod with an ARD link"                     namespace.create "{$BASE,\"lifecycle\":\"prod\",\"ard_link\":\"https://x/ard.docx\"}"
accepts "gpu on with a tier"                        namespace.create "{$BASE,\"gpu_enabled\":\"true\",\"gpu_tier\":\"standard\"}"

echo ""
echo "-- normalisation (the siglum bug: sentinel was compared in the wrong case)"
exports "siglum is upper-cased"                     namespace.create "{$BASE,\"siglum\":\"td01\"}"          INPUT_SIGLUM "TD01"
exports "tenant name is lower-cased"                namespace.create "{$BASE,\"tenant_name\":\"ACME\"}"     INPUT_TENANT_NAME "acme"
exports "email is lower-cased"                      namespace.create "{$BASE,\"requester_email\":\"A.B@ZZZ.COM\"}" INPUT_REQUESTER_EMAIL "a.b@zzz.com"

echo ""
echo "-- presence"
rejects "missing request_id"                        namespace.create "{\"requester_email\":\"a.b@zzz.com\",\"requested_at\":\"01/04/2026 13:47:48\",\"target_cluster\":\"qa-w1\",\"tenant_name\":\"acme\",\"siglum\":\"TD01\",\"cost_center\":\"\",\"lifecycle\":\"dev\"}" "request_id"
rejects "omitted cost centre is not the same as empty" namespace.create "{\"request_id\":\"REQ1\",\"requester_email\":\"a.b@zzz.com\",\"requested_at\":\"01/04/2026 13:47:48\",\"target_cluster\":\"qa-w1\",\"tenant_name\":\"acme\",\"siglum\":\"TD01\",\"lifecycle\":\"dev\"}" "cost_center"

echo ""
echo "-- the enforcement GitLab used to do for us"
rejects "unknown field"                             namespace.create "{$BASE,\"tenat_name\":\"typo\"}"      "Unknown field"
rejects "field belonging to another operation"      namespace.create "{$BASE,\"images\":\"nginx\"}"     "not accepted by operation"
rejects "target cluster off the option list"        namespace.create "{$BASE,\"target_cluster\":\"qa-w2\"}" "must be one of"
rejects "lifecycle off the option list"             namespace.create "{$BASE,\"lifecycle\":\"staging\"}"    "must be one of"
rejects "boolean that is not true/false"            namespace.create "{$BASE,\"gpu_enabled\":\"yes\"}"      "true or false"
rejects "unknown operation"                         namespace.destroy "$NS_MIN"                             "Unknown OPERATION"

echo ""
echo "-- formats"
rejects "cost centre with illegal characters"       namespace.create "{$BASE,\"cost_center\":\"XX YY\"}"    "format"
rejects "timestamp already in ISO is not accepted"  namespace.create "{$BASE,\"requested_at\":\"2026-04-01T13:47:48\"}" "MyITSM"
rejects "impossible month"                          namespace.create "{$BASE,\"requested_at\":\"01/13/2026 00:00:00\"}" "month"
rejects "impossible hour"                           namespace.create "{$BASE,\"requested_at\":\"01/01/2026 25:00:00\"}" "hour"
rejects "reserved namespace prefix"                 namespace.create "{$BASE,\"namespace_name\":\"dcsc-ds-x\"}" "reserved"

echo ""
echo "-- timestamps: pasted from MyITSM, stored as ISO"
exports "DD/MM/YYYY is converted to ISO on export"  namespace.create "$NS_MIN" INPUT_REQUESTED_TIMESTAMP "2026-04-01T13:47:48"
exports "day and month are not transposed"          namespace.create "{$BASE,\"requested_at\":\"03/11/2026 09:05:01\"}" INPUT_REQUESTED_TIMESTAMP "2026-11-03T09:05:01"

echo ""
echo "-- conditional fields"
rejects "prod without an ARD"                       namespace.create "{$BASE,\"lifecycle\":\"prod\"}"       "ard_link"
rejects "gpu on without a tier"                     namespace.create "{$BASE,\"gpu_enabled\":\"true\"}"     "gpu_tier"
exports "gpu off forces the literal None"           namespace.create "$NS_MIN"                              INPUT_GPU_TIER "None"
exports "ARD is blank on a dev request"             namespace.create "$NS_MIN"                              INPUT_ARD_LINK ""
# route_exception is dev-only. On a prod request it is hidden, so supplying it
# is not an error -- it is simply forced to its absent value.
exports "route exception forced off for prod"       namespace.create "{$BASE,\"lifecycle\":\"prod\",\"ard_link\":\"https://x\",\"route_exception\":\"true\"}" INPUT_ROUTE_EXCEPTION "false"

echo ""
echo "-- operation constants replace the old boolean trio"
exports "namespace.create sets CSO_CREATE false"    namespace.create "$NS_MIN"                              INPUT_CREATE_CSO "false"
exports "cso.create sets CSO_CREATE true"           cso.create       "{$BASE,\"egressip_allocation\":\"NONE\"}" INPUT_CREATE_CSO "true"
exports "namespace.decommission sets CSO false"     namespace.decommission "{\"request_id\":\"REQ1\",\"requester_email\":\"a.b@zzz.com\",\"requested_at\":\"01/04/2026 13:47:48\",\"target_cluster\":\"qa-w1\",\"tenant_name\":\"acme\",\"namespace_name\":\"dcsc-acme-a1b2\"}" INPUT_DECOMMISSION_CSO "false"
exports "cso.decommission sets CSO true"            cso.decommission       "{\"request_id\":\"REQ1\",\"requester_email\":\"a.b@zzz.com\",\"requested_at\":\"01/04/2026 13:47:48\",\"target_cluster\":\"qa-w1\",\"tenant_name\":\"acme\",\"namespace_name\":\"dcsc-ei-abc\"}" INPUT_DECOMMISSION_CSO "true"

echo ""
echo "-- decommission no longer demands a cost centre it never used"
accepts "decommission without a cost centre"        namespace.decommission "{\"request_id\":\"REQ1\",\"requester_email\":\"a.b@zzz.com\",\"requested_at\":\"01/04/2026 13:47:48\",\"target_cluster\":\"qa-w1\",\"tenant_name\":\"acme\",\"namespace_name\":\"dcsc-acme-a1b2\"}"

echo ""
echo "-- registry mirror, including the chained show_if"
MIRROR_BASE='"request_id":"REQ1","requester_email":"a.b@zzz.com","requested_at":"01/04/2026 13:47:48","target_cluster":"qa-w1","tenant_name":"acme","harbor_project":"dev-acme","registry_url":"https://reg.example.com","images":"library/nginx"'
accepts "external mirror without auth"              mirror.create "{$MIRROR_BASE}"
rejects "external mirror, auth on, no username"     mirror.create "{$MIRROR_BASE,\"registry_needs_credentials\":\"true\"}" "registry_username"
accepts "external mirror, auth on, credentials"     mirror.create "{$MIRROR_BASE,\"registry_needs_credentials\":\"true\",\"registry_username\":\"u\",\"registry_secret_ref\":\"s\"}"
rejects "registry url must be https"                mirror.create "{$MIRROR_BASE,\"registry_url\":\"http://reg.example.com\"}" "format"
# registry_auth is hidden for the internal types, and registry_username is
# hidden by registry_auth in turn -- the chain the fixed-point loop exists for.
exports "internal replication hides auth"           mirror.create "{$MIRROR_BASE,\"replication_type\":\"dcs-internal\"}" INPUT_REGISTRY_NEEDS_CREDENTIALS "false"
exports "internal replication hides username"       mirror.create "{$MIRROR_BASE,\"replication_type\":\"dcs-internal\"}" INPUT_REGISTRY_USERNAME ""

echo ""
echo "-- malformed payloads"
rejects "payload that is not JSON"                  namespace.create "not json"        "JSON object"
rejects "payload that is a JSON array"              namespace.create "[1,2,3]"         "JSON object"

echo ""
echo "==========================================================================="
printf "  %d passed, %d failed\n" "$PASS" "$FAIL"
echo "==========================================================================="
[ "$FAIL" -eq 0 ]
