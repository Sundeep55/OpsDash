#!/bin/bash
# =============================================================================
# scaffold-mirror.sh  (was scaffold-registry-mirror.sh, in its own repo)
#
# Adds registry replication rules for an existing namespace.
#
# WHAT CHANGED IN THE MERGE
# -------------------------
# This script used to live in a separate repository and therefore had to clone
# dcs-customer-instances into /tmp, operate on the clone, and push from there.
# Now that it lives in customer-instances itself, the checkout it needs is the
# one it is already running in. clone_target_repo is gone, CLONE_DIR is gone,
# and every path is repo-relative exactly as in scaffold-namespace.sh.
#
# That removes: a full clone per run, a second set of credentials in the URL, a
# TARGET_BASE_BRANCH knob that could silently mirror against a stale branch, and
# the class of bug where the script validated one checkout and committed to
# another.
#
# Validation of individual inputs is in request-schema.yaml, enforced by
# load-payload.sh. What stays here is the per-element checking of the
# comma-separated image and tag lists, which is a list-shape rule the schema
# cannot express.
# =============================================================================
set -e

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_HERE}/common.sh"
source "${_HERE}/load-payload.sh"

# --- List-shape validation ---------------------------------------------------
function validate_images() {
    log_info "=== Validating image and tag lists ==="

    IFS=',' read -ra IMAGE_ARRAY <<< "$INPUT_IMAGE_NAMES"
    IFS=',' read -ra TAG_ARRAY <<< "$INPUT_IMAGE_TAGS"

    [[ ${#IMAGE_ARRAY[@]} -eq 0 ]] && { log_error "IMAGE_NAME is required."; exit 1; }

    local i IMG TAG
    for i in "${!IMAGE_ARRAY[@]}"; do
        IMG=$(echo "${IMAGE_ARRAY[$i]}" | xargs)

        [[ "$IMG" == "**" ]] && { log_error "IMAGE_NAME '**' is not allowed."; exit 1; }
        if [[ ! "$IMG" =~ ^[a-zA-Z0-9_./*?{},:-]+$ ]]; then
            log_error "IMAGE_NAME contains invalid characters: '$IMG'"
            exit 1
        fi
        if [[ "$IMG" =~ \*\* && ! "$IMG" =~ (^|/)\*\*(/|$) ]]; then
            log_error "'**' must be a standalone path component: '$IMG'"
            exit 1
        fi
    done

    for i in "${!TAG_ARRAY[@]}"; do
        TAG=$(echo "${TAG_ARRAY[$i]}" | xargs)
        if [[ -n "$TAG" ]]; then
            if [[ ! "$TAG" =~ ^[a-zA-Z0-9_.+*?{},:-]+$ ]]; then
                log_error "IMAGE_TAG contains invalid characters: '$TAG'"
                exit 1
            fi
            if [[ "$TAG" == */* ]]; then
                log_error "IMAGE_TAG must not contain '/': '$TAG'"
                exit 1
            fi
            [[ "$TAG" == "**" ]] && { log_error "IMAGE_TAG '**' is not needed — omit IMAGE_TAG to replicate all tags."; exit 1; }
        fi
    done

    log_info "Image and tag lists valid."
}

# --- Prepare Variables -------------------------------------------------------
function prepare_variables() {
    log_info "=== Preparing Variables ==="
    REPL_SUFFIX=$(head -c 100 /dev/urandom | tr -dc 'a-z0-9' | head -c 4)

    REGISTRY_NAME="dcsc-${INPUT_TENANT_NAME}-registry-${REPL_SUFFIX}"
    CUSTOMER_DIR="${INPUT_TARGET_CLUSTER}/${INPUT_TENANT_NAME}"

    if [[ "$INPUT_HARBOR_PROJECT" =~ ^(dev|prod)- ]]; then
        NS_FOLDER_NAME="${INPUT_HARBOR_PROJECT#*-}"
    else
        NS_FOLDER_NAME="${INPUT_HARBOR_PROJECT}"
    fi

    if [[ "$INPUT_REPLICATION_TYPE" == "dcs-internal" ]]; then
        REGISTRY_NAME="${REGISTRY_NAME}-internal"
    elif [[ "$INPUT_REPLICATION_TYPE" == "dcs-internal-div-nat" ]]; then
        REGISTRY_NAME="${REGISTRY_NAME}-internal-div-nat"
    else
        REGISTRY_NAME="${REGISTRY_NAME}-external"
    fi

    NS_DIR="${CUSTOMER_DIR}/${NS_FOLDER_NAME}"
    REPLICATION_VALUES_FILE="${NS_DIR}/values-registry-mirror.yaml"
    CHART_FILE="${NS_DIR}/Chart.yaml"
    TENANT_METADATA_FILE="${CUSTOMER_DIR}/tenant-metadata.yaml"
    TEMPLATE_DIR="./customers-templates"
    REPLICATION_CATEGORY="dockerRegistryReplications"
    FLATTENING_LEVEL="-1"
    PASSWORD_KEY="attribute.secret"
    REGISTRY_CONFIG_CHART_VERSION="${REGISTRY_CONFIG_CHART_VERSION:-3.4.1}"

    ROBOT_ACCOUNT_ENV="${ROBOT_ACCOUNT_ENV:-robot-dcsc-mirroring-account}"
    ROBOT_ACCOUNT_ENV_PASS_KEY="${ROBOT_ACCOUNT_ENV_PASS_KEY:-${PASSWORD_KEY}}"
    ROBOT_ACCOUNT_ENV_PASS_SECRET="${ROBOT_ACCOUNT_ENV_PASS_SECRET:-customer-mirror-robot-account}"

    ROBOT_ACCOUNT_ENV_DIV_NAT="${ROBOT_ACCOUNT_ENV_DIV_NAT:-robot-dcsc-mirroring-account-divisional}"
    ROBOT_ACCOUNT_ENV_PASS_KEY_DIV_NAT="${ROBOT_ACCOUNT_ENV_PASS_KEY_DIV_NAT:-${PASSWORD_KEY}}"
    ROBOT_ACCOUNT_ENV_PASS_SECRET_DIV_NAT="${ROBOT_ACCOUNT_ENV_PASS_SECRET_DIV_NAT:-customer-mirror-robot-account-divisional}"

    NEW_BRANCH_NAME="feat/${REGISTRY_NAME}"

    CURRENT_OFFSET=$(date +%z | sed 's/^\(...\)\(..\)$/\1:\2/')
    REQUESTED_TIMESTAMP="${INPUT_REQUESTED_TIMESTAMP}${CURRENT_OFFSET}"
    PROVISION_TIMESTAMP="$(date +'%Y-%m-%dT%H:%M:%S')${CURRENT_OFFSET}"

    log_info "Variables prepared."
}

# Reuse an existing registry entry when this endpoint URL is already registered
# for the tenant, so a second image against the same registry does not create a
# duplicate. Must run before sanity_checks, which asserts the branch name is
# free -- this function can change that name.
function check_existing_registry() {
    log_info "=== Checking for Existing Registry URL ==="
    if [[ -f "$TENANT_METADATA_FILE" ]]; then
        local FOUND_REG_NAME
        FOUND_REG_NAME=$(yq e ".active_registry_mirrors[]? | select(.endpoint_url == \"${INPUT_REGISTRY_URL}\") | .registry_name" "$TENANT_METADATA_FILE" 2>/dev/null | head -n 1 || true)

        if [[ -n "$FOUND_REG_NAME" && "$FOUND_REG_NAME" != "null" ]]; then
            log_info "Match found! URL ${INPUT_REGISTRY_URL} is already registered."
            log_info "Reusing existing registry name: ${FOUND_REG_NAME}"
            REGISTRY_NAME="$FOUND_REG_NAME"
            NEW_BRANCH_NAME="feat/${REGISTRY_NAME}-${REPL_SUFFIX}"
        else
            log_info "No matching URL found. Creating new registry: ${REGISTRY_NAME}"
        fi
    else
        log_info "Metadata file not found. Creating new registry: ${REGISTRY_NAME}"
    fi
}

function sanity_checks() {
    log_info "=== Sanity Checks ==="

    if [[ ! -d "$CUSTOMER_DIR" ]]; then
        log_error "Tenant directory does not exist: $CUSTOMER_DIR"
        exit 1
    fi

    if [[ ! -d "$NS_DIR" ]]; then
        log_error "Namespace directory '${NS_FOLDER_NAME}' does not exist under tenant '${INPUT_TENANT_NAME}'."
        exit 1
    fi

    if [[ ! -f "$CHART_FILE" ]]; then
        log_error "Chart.yaml not found in namespace directory: ${NS_DIR}"
        exit 1
    fi

    if git ls-remote --exit-code --heads "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME" > /dev/null 2>&1; then
        log_error "Branch '$NEW_BRANCH_NAME' already exists."
        exit 1
    fi

    if [[ -f "$REPLICATION_VALUES_FILE" ]]; then
        log_info "Found existing values-registry-mirror.yaml."
        MIRROR_EXISTS=true
    else
        log_info "No existing values-registry-mirror.yaml found. Will create."
        MIRROR_EXISTS=false
    fi
}

function scaffold_mirror_config() {
    log_info "=== Scaffolding Registry Mirror Config ==="
    cp "${TEMPLATE_DIR}/values-registry-mirror.yaml.tpl" "$REPLICATION_VALUES_FILE"
    sed -i "s|__SECRET_NAMESPACE__|${NS_FOLDER_NAME}|g" "$REPLICATION_VALUES_FILE"
    add_chart_dependency
}

function add_chart_dependency() {
    local EXISTING_DEP
    EXISTING_DEP=$(yq e '.dependencies[] | select(.name == "dcs-registry-config") | .name' "$CHART_FILE" 2>/dev/null || true)
    if [[ -n "$EXISTING_DEP" ]]; then
        return 0
    fi
    yq e -i ".dependencies += [{
        \"name\": \"dcs-registry-config\",
        \"version\": \"${REGISTRY_CONFIG_CHART_VERSION}\",
        \"repository\": \"oci://${HARBOR_LOCAL_URL}/${HARBOR_OCI_PROJECT}\"
    }]" "$CHART_FILE"
}

# --- Append (Registry + Multiple Replications) ---
function append_replication() {
    log_info "=== Appending Registry and Replication Rules ==="
    local TARGET_VALUES="$REPLICATION_VALUES_FILE"

    # 1. Handle the Registry (Once)
    local REG_USER="" REG_SECRET="" REG_PASS="" REG_NAMESPACE="" HAS_AUTH="false"

    if [[ "$INPUT_REPLICATION_TYPE" == "dcs-internal" ]]; then
        REG_USER="${ROBOT_ACCOUNT_ENV}"
        REG_PASS="${ROBOT_ACCOUNT_ENV_PASS_KEY}"
        REG_SECRET="${ROBOT_ACCOUNT_ENV_PASS_SECRET}"
        REG_NAMESPACE="dcs-crossplane"
        HAS_AUTH="true"
    elif [[ "$INPUT_REPLICATION_TYPE" == "dcs-internal-div-nat" ]]; then
        REG_USER="${ROBOT_ACCOUNT_ENV_DIV_NAT}"
        REG_PASS="${ROBOT_ACCOUNT_ENV_PASS_KEY_DIV_NAT}"
        REG_SECRET="${ROBOT_ACCOUNT_ENV_PASS_SECRET_DIV_NAT}"
        REG_NAMESPACE="dcs-crossplane"
        HAS_AUTH="true"
    elif [[ "$INPUT_REGISTRY_NEEDS_CREDENTIALS" == "true" ]]; then
        REG_USER="${INPUT_REGISTRY_USERNAME}"
        REG_SECRET="${INPUT_REGISTRY_SECRET_REF}"
        REG_PASS="password"
        HAS_AUTH="true"
    fi

    local EXISTING_REG
    EXISTING_REG=$(yq e ".\"dcs-registry-config\".registries[] | select(.name == \"${REGISTRY_NAME}\") | .name" "$TARGET_VALUES" 2>/dev/null || true)

    if [[ -n "$EXISTING_REG" ]]; then
        # Upgrade auth if needed
        local EXISTING_SECRET
        EXISTING_SECRET=$(yq e ".\"dcs-registry-config\".registries[] | select(.name == \"${REGISTRY_NAME}\") | .secretName // \"\"" "$TARGET_VALUES" 2>/dev/null || true)

        if [[ "$HAS_AUTH" == "true" && ( -z "$EXISTING_SECRET" || "$EXISTING_SECRET" == "null" ) ]]; then
            local EXTRA_FIELD=""
            if [[ -n "$REG_NAMESPACE" ]]; then
                if [[ "$INPUT_REPLICATION_TYPE" == "dcs-internal" || "$INPUT_REPLICATION_TYPE" == "dcs-internal-div-nat" ]]; then
                    EXTRA_FIELD=", \"dcsNamespace\": \"${REG_NAMESPACE}\""
                else
                    EXTRA_FIELD=", \"dcs-namespace\": \"${REG_NAMESPACE}\""
                fi
            fi
            yq e -i "(.\"dcs-registry-config\".registries[] | select(.name == \"${REGISTRY_NAME}\")) |= . + {\"accessId\": \"${REG_USER}\", \"secretName\": \"${REG_SECRET}\", \"secretKey\": \"${REG_PASS}\"${EXTRA_FIELD}}" "$TARGET_VALUES"
        fi
    else
        # New registry — create it
        if [[ "$HAS_AUTH" == "true" ]]; then
            local EXTRA_FIELD=""
            if [[ -n "$REG_NAMESPACE" ]]; then
                if [[ "$INPUT_REPLICATION_TYPE" == "dcs-internal" || "$INPUT_REPLICATION_TYPE" == "dcs-internal-div-nat" ]]; then
                    EXTRA_FIELD=", \"dcsNamespace\": \"${REG_NAMESPACE}\""
                else
                    EXTRA_FIELD=", \"dcs-namespace\": \"${REG_NAMESPACE}\""
                fi
            fi
            yq e -i ".\"dcs-registry-config\".registries += [{
                \"name\": \"${REGISTRY_NAME}\",
                \"endpointUrl\": \"${INPUT_REGISTRY_URL}\",
                \"providerName\": \"${INPUT_REGISTRY_PROVIDER}\",
                \"accessId\": \"${REG_USER}\",
                \"secretName\": \"${REG_SECRET}\",
                \"secretKey\": \"${REG_PASS}\"${EXTRA_FIELD}
            }]" "$TARGET_VALUES"
        else
            yq e -i ".\"dcs-registry-config\".registries += [{
                \"name\": \"${REGISTRY_NAME}\",
                \"endpointUrl\": \"${INPUT_REGISTRY_URL}\",
                \"providerName\": \"${INPUT_REGISTRY_PROVIDER}\"
            }]" "$TARGET_VALUES"
        fi
    fi

    # 2. Iterate through multiple images to build Replication rules
    IFS=',' read -ra IMAGE_ARRAY <<< "$INPUT_IMAGE_NAMES"
    IFS=',' read -ra TAG_ARRAY <<< "$INPUT_IMAGE_TAGS"
    local TAG_COUNT=${#TAG_ARRAY[@]}

    local i
    for i in "${!IMAGE_ARRAY[@]}"; do
        local CURRENT_IMAGE CURRENT_TAG SAFE_IMAGE_SHORT REPLICATION_NAME IMAGE_LABEL FILTERS EXISTING_REPL

        CURRENT_IMAGE=$(echo "${IMAGE_ARRAY[$i]}" | xargs)

        # Smart tag mapping
        if [[ $TAG_COUNT -eq 1 ]]; then
            CURRENT_TAG=$(echo "${TAG_ARRAY[0]}" | xargs) # Apply single tag to all images
        else
            CURRENT_TAG=$(echo "${TAG_ARRAY[$i]:-}" | xargs) # Apply corresponding tag, or empty
        fi

        SAFE_IMAGE_SHORT=$(echo "${CURRENT_IMAGE##*/}" | sed 's/\*\*/all/g' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
        SAFE_IMAGE_SHORT="${SAFE_IMAGE_SHORT:-image}"
        REPLICATION_NAME="dcsc-repl-${INPUT_TENANT_NAME}-${SAFE_IMAGE_SHORT}-${REPL_SUFFIX}"

        if [[ -n "$CURRENT_TAG" ]]; then
            FILTERS="[{\"name\": \"${CURRENT_IMAGE}\"}, {\"tag\": \"${CURRENT_TAG}\"}]"
            IMAGE_LABEL="${CURRENT_IMAGE}:${CURRENT_TAG}"
            EXISTING_REPL=$(yq e ".\"dcs-registry-config\".${REPLICATION_CATEGORY}[] | select(.registry == \"${REGISTRY_NAME}\") | select(.filters[] | .name == \"${CURRENT_IMAGE}\") | select(.filters[] | .tag == \"${CURRENT_TAG}\") | .name" "$TARGET_VALUES" 2>/dev/null || true)
        else
            FILTERS="[{\"name\": \"${CURRENT_IMAGE}\"}]"
            IMAGE_LABEL="${CURRENT_IMAGE} (all tags)"
            EXISTING_REPL=$(yq e ".\"dcs-registry-config\".${REPLICATION_CATEGORY}[] | select(.registry == \"${REGISTRY_NAME}\") | select(.filters[] | .name == \"${CURRENT_IMAGE}\") | select(.filters | all(has(\"tag\") | not)) | .name" "$TARGET_VALUES" 2>/dev/null || true)
        fi

        if [[ -n "$EXISTING_REPL" ]]; then
            log_info "Replication for '${IMAGE_LABEL}' already exists ('${EXISTING_REPL}'). Skipping."
            continue
        fi

        log_info "Adding replication rule for ${IMAGE_LABEL}..."
        yq e -i ".\"dcs-registry-config\".${REPLICATION_CATEGORY} += [{
            \"name\": \"${REPLICATION_NAME}\",
            \"description\": \"Mirror ${IMAGE_LABEL} to ${INPUT_HARBOR_PROJECT}\",
            \"registry\": \"${REGISTRY_NAME}\",
            \"destinationNamespace\": \"${INPUT_HARBOR_PROJECT}\",
            \"flatteningLevel\": ${FLATTENING_LEVEL},
            \"schedule\": \"0 0 0 * * *\",
            \"filters\": ${FILTERS}
        }]" "$TARGET_VALUES"

        if [[ -f "$TENANT_METADATA_FILE" ]]; then
            yq e -i "
                .active_registry_mirrors += [{
                    \"registry_name\": \"${REGISTRY_NAME}\",
                    \"requester_email\": \"${INPUT_REQUESTER_EMAIL}\",
                    \"request_id\": \"${INPUT_REQUEST_ID}\",
                    \"namespace\": \"${NS_FOLDER_NAME}\",
                    \"endpoint_url\": \"${INPUT_REGISTRY_URL}\",
                    \"image\": \"${CURRENT_IMAGE}\",
                    \"tag\": \"${CURRENT_TAG:-}\",
                    \"harbor_project\": \"${INPUT_HARBOR_PROJECT}\",
                    \"replication_name\": \"${REPLICATION_NAME}\",
                    \"requested_timestamp\": \"${REQUESTED_TIMESTAMP}\",
                    \"provision_timestamp\": \"${PROVISION_TIMESTAMP}\"
                }]
            " "$TENANT_METADATA_FILE"
        fi
    done
}

function run_git_ops() {
    log_info "=== Git Operations ==="
    git config --global user.email "${GITLAB_USER_EMAIL}"
    git config --global user.name "${GITLAB_USER_NAME}"
    git checkout -b "$NEW_BRANCH_NAME"

    git add "$REPLICATION_VALUES_FILE"
    git add "$CHART_FILE"
    if [ -f "$TENANT_METADATA_FILE" ]; then
        git add "$TENANT_METADATA_FILE"
    fi

    if git diff --cached --quiet; then
        log_info "No changes detected. Skipping commit and push."
        return 0
    fi

    git commit -m "feat: Add registry mirror(s) for ${REGISTRY_NAME} in ${INPUT_TENANT_NAME}"
    git push "https://${CI_SERVER_HOST}:${GITLAB_TOKEN}@${CI_SERVER_HOST}/${CI_PROJECT_PATH}.git" "$NEW_BRANCH_NAME"
    echo ""
    log_info "Branch '$NEW_BRANCH_NAME' pushed."
    echo ""
    echo "---------------------------------------------------------------------------"
    echo "| **  Please create a Merge Request from this branch to continue.   **    |"
    echo "---------------------------------------------------------------------------"
}

function print_summary() {
    echo "=== Mirror Configuration ==="
    echo "Tenant:                     $INPUT_TENANT_NAME"
    echo "Cluster:                    $INPUT_TARGET_CLUSTER"
    echo "Harbor Project:             $INPUT_HARBOR_PROJECT"
    echo "Namespace Directory:        $NS_DIR"
    echo "Registry Name:              $REGISTRY_NAME"
    echo "Registry URL:               $INPUT_REGISTRY_URL"
    echo "Auth Required:              $INPUT_REGISTRY_NEEDS_CREDENTIALS"
    echo "Images Requested:           $INPUT_IMAGE_NAMES"
    echo "Tags Requested:             ${INPUT_IMAGE_TAGS:-<all>}"
    echo "Target Branch:              $NEW_BRANCH_NAME"
    echo "---------------------------------------------------------------------------"
}

# --- Main Execution Flow ---
enable_debug_if_requested

validate_images
prepare_variables
check_existing_registry
sanity_checks
print_summary

if [[ "$MIRROR_EXISTS" != "true" ]]; then
    scaffold_mirror_config
else
    add_chart_dependency
fi

append_replication
run_git_ops
