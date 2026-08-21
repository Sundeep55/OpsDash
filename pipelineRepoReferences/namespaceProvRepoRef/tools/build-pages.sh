#!/bin/bash
# =============================================================================
# build-pages.sh — assemble the GitLab Pages site into public/.
#
#   ./tools/build-pages.sh [output-dir]
#
# Produces three things:
#
#   schema.json   request-schema.yaml converted. The form renders itself from
#                 this, so a field added to the schema appears on the form with
#                 no change to any file in pages/.
#
#   index.json    every cluster, tenant and namespace that exists in this
#                 checkout, plus each tenant's siglum, cost centre and
#                 requester.
#
#   the static files from pages/
#
# WHY index.json IS WORTH THE TROUBLE
# -----------------------------------
# This repository *is* dcs-customer-instances, so the Pages job is already
# standing in a full checkout of every tenant. Emitting the index costs one
# walk of the tree and removes the single worst piece of friction in the current
# process: operators writing tenant and namespace names down by hand before
# triggering a pipeline, and finding out from a failed run when they get one
# wrong.
#
# It is only as fresh as the last merge to main — which is exactly when
# namespaces come into existence, since they are created by merging a scaffold
# branch. The form shows the commit and timestamp so nobody has to guess.
#
# What goes in is what any project member can already read from the repository,
# so this adds no exposure that the repo itself does not. It does concentrate
# it, which is a reason to keep Pages access control on.
# =============================================================================
set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# REPO_ROOT lets the test suite point this at a fixture tree instead of
# requiring cluster directories to exist in the repo under test.
ROOT="${REPO_ROOT:-$(dirname "$HERE")}"
OUT="${1:-${ROOT}/public}"
SCHEMA="${SCHEMA_FILE:-${ROOT}/request-schema.yaml}"
PAGES_DIR="${PAGES_DIR:-${ROOT}/pages}"

command -v yq >/dev/null 2>&1 || { echo "yq is not on PATH."; exit 1; }
[ -f "$SCHEMA" ] || { echo "Schema not found at $SCHEMA"; exit 1; }

echo "==========================================================================="
echo "                            Building Pages site                            "
echo "==========================================================================="

rm -rf "$OUT"
mkdir -p "$OUT"

# --- 1. the schema ---------------------------------------------------------
yq -o json '.' "$SCHEMA" > "$OUT/schema.json"
echo "-> schema.json ($(yq -r '.fields | keys | length' "$SCHEMA") fields, $(yq -r '.operations | keys | length' "$SCHEMA") operations)"

# --- 2. the index ----------------------------------------------------------
# Clusters come from the schema rather than from whatever directories happen to
# exist, so a stray folder cannot invent a cluster the pipeline would reject.
CLUSTERS=$(yq -r '.fields.target_cluster.options[]' "$SCHEMA")

GENERATED_AT=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
COMMIT="${CI_COMMIT_SHORT_SHA:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)}"

{
    printf '{\n'
    printf '  "generated_at": "%s",\n' "$GENERATED_AT"
    printf '  "commit": "%s",\n' "$COMMIT"
    printf '  "clusters": {\n'

    first_cluster=1
    for cluster in $CLUSTERS; do
        [ -d "${ROOT}/${cluster}" ] || continue
        [ $first_cluster -eq 1 ] || printf ',\n'
        first_cluster=0
        printf '    "%s": {\n' "$cluster"

        first_tenant=1
        for tenant_path in "${ROOT}/${cluster}"/*; do
            [ -d "$tenant_path" ] || continue
            tenant=$(basename "$tenant_path")
            # Dot-directories are the decommissioned archives, not tenants.
            case "$tenant" in .*) continue ;; esac

            meta="${tenant_path}/tenant-metadata.yaml"
            siglum=""; cost_center=""; requester=""
            if [ -f "$meta" ]; then
                siglum=$(yq -r '.siglum // ""' "$meta" 2>/dev/null || echo "")
                cost_center=$(yq -r '.cost_center // ""' "$meta" 2>/dev/null || echo "")
                requester=$(yq -r '.requester // ""' "$meta" 2>/dev/null || echo "")
            fi

            # Namespaces are read from the directory tree, not from
            # tenant-metadata.yaml: the tree is the thing ArgoCD acts on, and a
            # tenant provisioned before the metadata file existed still has one.
            namespaces=""
            for ns_path in "$tenant_path"/*; do
                [ -d "$ns_path" ] || continue
                ns=$(basename "$ns_path")
                case "$ns" in .*) continue ;; esac
                [ -f "$ns_path/values.yaml" ] || continue
                if [ -z "$namespaces" ]; then namespaces="\"$ns\""; else namespaces="$namespaces, \"$ns\""; fi
            done

            [ $first_tenant -eq 1 ] || printf ',\n'
            first_tenant=0
            printf '      "%s": { "namespaces": [%s], "siglum": "%s", "cost_center": "%s", "requester": "%s" }' \
                "$tenant" "$namespaces" "$siglum" "$cost_center" "$requester"
        done

        printf '\n    }'
    done

    printf '\n  }\n}\n'
} > "$OUT/index.json"

# A malformed index would fail silently in the browser -- the form would just
# show empty picklists -- so it is parsed here instead.
yq -p json -o json -e '.' "$OUT/index.json" >/dev/null 2>&1 || { echo "ERROR: generated index.json is not valid JSON"; exit 1; }
echo "-> index.json ($(yq -p json -o json -r '[.clusters[] | keys | .[]] | length' "$OUT/index.json") tenants across $(yq -p json -o json -r '.clusters | keys | length' "$OUT/index.json") cluster(s))"

# --- 3. where to send requests ---------------------------------------------
# GitLab tells the job all of this for free, so the operator should never be
# asked for any of it. None of these are secrets: the server URL and project id
# are visible to anyone who can reach the project at all.
#
# Deliberately NOT written here: a token. This file is published as a static
# asset, so anything in it is readable by everyone who can load the site. See
# pages/README.md for the ways to authenticate that do not require that.
cat > "$OUT/config.json" <<JSON
{
  "gitlab_url": "${CI_SERVER_URL:-}",
  "project_id": "${CI_PROJECT_ID:-}",
  "project_path": "${CI_PROJECT_PATH:-}",
  "ref": "${CI_DEFAULT_BRANCH:-main}"
}
JSON
yq -p json -o json -e '.' "$OUT/config.json" >/dev/null 2>&1 || { echo "ERROR: generated config.json is not valid JSON"; exit 1; }
if [ -n "${CI_PROJECT_ID:-}" ]; then
    echo "-> config.json (project ${CI_PROJECT_PATH} #${CI_PROJECT_ID} on ${CI_SERVER_URL}, ref ${CI_DEFAULT_BRANCH:-main})"
else
    echo "-> config.json (empty -- not running in CI, the form will ask for these)"
fi

# --- 4. the static files ---------------------------------------------------
cp "${PAGES_DIR}/"* "$OUT/"
echo "-> copied $(ls -1 "${PAGES_DIR}" | wc -l | tr -d ' ') files from pages/"

echo "==========================================================================="
echo "  Site built into $OUT"
echo "==========================================================================="
