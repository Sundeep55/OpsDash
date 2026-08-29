#!/bin/bash
set -e

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${_HERE}/common.sh"
source "${_HERE}/load-payload.sh"

function prepare_variables() {
    echo "==========================================================================="
    echo "                          Preparing Variables                              "
    echo "==========================================================================="
    log_info "Preparing Variables..."

    # Default var values
    SUFFIX_MAX_CHARS=4
    # We are limited by the helm to have a maximum 52 chars for argocd app name 
    NS_MAX_CHARS=50
    # Number of fix characters dcsc--2f9w
    NS_FIX_CHARS=10
    # Number of characters dcsc-ds--9g4q  
    DS_FIX_CHARS=13

    # Generate chars for random suffix string
    RANDOM_SUFFIX=$({ shuf -n 2 -re {a..z}; shuf -n 2 -re {0..9}; } | shuf | tr -d '\n' | head -c $SUFFIX_MAX_CHARS)
    RANDOM_SUFFIX10=$({ shuf -n 5 -re {a..z}; shuf -n 5 -re {0..9}; } | shuf | tr -d '\n' | head -c 10)

    # Kubernetes label value doesn't allow '\'. Normalize the value.
    COST_CENTER_LABEL_VALUE="${INPUT_COST_CENTER//\//-}"

    # Tenant name Suffix Logic
    TENANT_DIR="${INPUT_TARGET_CLUSTER}/${INPUT_TENANT_NAME}"

    if [[ -d "$TENANT_DIR" ]]; then
        log_info "Tenant  $TENANT_DIR exists."
        TENANT_NAME=$INPUT_TENANT_NAME
    else
        TENANT_NAME="${INPUT_TENANT_NAME}-${RANDOM_SUFFIX}"
        log_info "We will generate a new tenant $TENANT_NAME"
    fi
    
    CUSTOMER_DIR="${INPUT_TARGET_CLUSTER}/${TENANT_NAME}"

    if [[ -z "$INPUT_SUB_TENANT" ]]; then
        INPUT_SUB_TENANT="dcsc-$TENANT_NAME"
        log_info "No Sub Tenant given, proceeding with main Tenant"
    fi

    if [[ "$INPUT_SUB_TENANT" != "dcsc-$TENANT_NAME"* ]]; then
        INPUT_SUB_TENANT="dcsc-$TENANT_NAME-$INPUT_SUB_TENANT"
    fi

    # Check if user provided an EXACT existing project to UPDATE
    if [ -d "${CUSTOMER_DIR}/${INPUT_SUB_TENANT}" ]; then
        TENANT_PROJECT="$INPUT_SUB_TENANT"
        log_info "Existing project provided for update: $INPUT_SUB_TENANT"
    else
        # Tenant Project Prefix and Suffix Logic
        if [[ "$INPUT_SUB_TENANT" == dcsc-* ]]; then
            INPUT_SUB_TENANT="${INPUT_SUB_TENANT#dcsc-}"
        else
            INPUT_SUB_TENANT="$INPUT_SUB_TENANT"
        fi

        MAX_PROJECT_CHARS=$((NS_MAX_CHARS - NS_FIX_CHARS))

        # if [[ ${#TENANT_PROJECT_INPUT} -gt $MAX_PROJECT_CHARS ]]; then
        #     log_info "Warning: Tenant project exceeds $NS_MAX_CHARS characters. Truncating."
        #     TENANT_PROJECT_INPUT=$(echo "$TENANT_PROJECT_INPUT" | cut -c 1-"$MAX_PROJECT_CHARS")
        #     log_info "Warning: New namespace name dcsc-${TENANT_PROJECT_INPUT}-${RANDOM_SUFFIX}"
        # fi

        TENANT_PROJECT="dcsc-${INPUT_SUB_TENANT}"
    fi

    # Calculate expiration dates if route exception is enabled
    if [[ "$INPUT_ROUTE_EXCEPTION" == "true" ]]; then
        EXCEPTION_GRANTED_DATE=$(date +'%Y-%m-%d')
        # Adds exactly 90 days to the granted date
        EXCEPTION_EXPIRES_DATE=$(date -d "+90 days" +'%Y-%m-%d')
        export EXCEPTION_GRANTED_DATE EXCEPTION_EXPIRES_DATE
    fi

    # Set Vars
    CURRENT_OFFSET=$(date +%z | sed 's/^\(...\)\(..\)$/\1:\2/')
    REQUESTED_TIMESTAMP="${REQUESTED_TIMESTAMP}${CURRENT_OFFSET}"
    PROVISION_TIMESTAMP=$(date +'%Y-%m-%dT%H:%M:%S')
    PROVISION_TIMESTAMP="${PROVISION_TIMESTAMP}${CURRENT_OFFSET}"

    PROJECT_DIR="${CUSTOMER_DIR}/${TENANT_PROJECT}"
    VALUES_FILE="${PROJECT_DIR}/values.yaml"
    CHART_FILE="${PROJECT_DIR}/Chart.yaml"
    HELMIGNORE_FILE="${PROJECT_DIR}/.helmignore"
    TENANT_METADATA_FILE="${CUSTOMER_DIR}/tenant-metadata.yaml"
    TEMPLATE_DIR="${PROVISIONER_BASE_PATH}/customers-templates"
    IPPOOL_FILE="${INPUT_TARGET_CLUSTER}/egressip-pool.yaml"
    EGRESSIP_NAME="dcsc-ei-${RANDOM_SUFFIX10}"
    
    IS_EXISTING_PROJECT="false"
    if [ -d "$PROJECT_DIR" ]; then
        IS_EXISTING_PROJECT="true"
        NEW_BRANCH_NAME="feat/update-${TENANT_PROJECT}-$(date +%s)"
        log_info "Existing project detected. Operating in UPDATE mode."
    else
        NEW_BRANCH_NAME="feat/onboard-${TENANT_PROJECT}"
        log_info "New project detected. Operating in CREATION mode."
    fi

    # Export calculated variables
    export TENANT_NAME TENANT_PROJECT PROVISION_TIMESTAMP REQUESTED_TIMESTAMP CUSTOMER_DIR RANDOM_SUFFIX EGRESSIP_NAME COST_CENTER_LABEL_VALUE IS_EXISTING_PROJECT

    log_info "Variables prepared."
    log_info "Timestamps set to Zone: CET ($CURRENT_OFFSET)"
}

function sanity_checks() {
    echo "==========================================================================="
    echo "                             Sanity Checks                                 "
    echo "==========================================================================="
    log_info "Running Sanity Checks..."

    if [ -n "${INPUT_MODE:-}" ]; then
        if [ "$INPUT_MODE" = "update" ] && [ "$IS_EXISTING_PROJECT" != "true" ]; then
            echo "==========================================================================="
            log_error "Update requested, but '$PROJECT_DIR' does not exist."
            log_error "Check the sub-tenant name, or use the create operation instead."
            echo "==========================================================================="
            exit 1
        fi
        if [ "$INPUT_MODE" = "create" ] && [ "$IS_EXISTING_PROJECT" = "true" ]; then
            echo "==========================================================================="
            log_error "Create requested, but '$PROJECT_DIR' already exists."
            log_error "Use the update operation to change it."
            echo "==========================================================================="
            exit 1
        fi
    fi

    # Check Branch
    if git ls-remote --exit-code --heads origin "$NEW_BRANCH_NAME" > /dev/null 2>&1; then
        log_error "Branch '$NEW_BRANCH_NAME' already exists in dcs-customer-instances."
        exit 1
    fi

    # Check Local Dir (Allows updates if IS_EXISTING_PROJECT is true and values.yaml exists)
    if [ "$IS_EXISTING_PROJECT" == "true" ] && [ ! -f "$PROJECT_DIR/values.yaml" ]; then
        log_error "Project path already exists but values.yaml is missing: $PROJECT_DIR"
        exit 1
    fi

    # Check if the argocd app name will be unique (ignoring dcsc-cso paths AND skipping if updating)
    if [ "$IS_EXISTING_PROJECT" == "false" ]; then
        MATCHING_PROJECT_DIR=$(find . -mindepth 3 -maxdepth 3 -type d -name "$TENANT_PROJECT" ! -path "*dcsc-cso-${TENANT_NAME}" -print -quit)
        if [[ -n "$MATCHING_PROJECT_DIR" ]]; then
          log_error "The project '$TENANT_PROJECT' already exists at path: '$MATCHING_PROJECT_DIR'"
          log_error "We need a unique project name that will be used for the ArgoCD app name and registry project name."
          exit 1
        fi
    fi
}

function update_metadata() {
    echo "==========================================================================="
    echo "                    Scaffolding - Metadata Update                          "
    echo "==========================================================================="
    log_info "Updating Metadata..."

    if [ ! -d "$CUSTOMER_DIR" ]; then
        log_info "Tenant directory does not exist. Creating: $CUSTOMER_DIR"
        mkdir -p "$CUSTOMER_DIR"
    fi

    # CREATE BASE FILE (If brand new tenant)
    if [ ! -f "$TENANT_METADATA_FILE" ]; then
      log_info "Creating base tenant metadata file..."
      yq -n '
        .tenant_name = strenv(TENANT_NAME) |
        .requester = strenv(INPUT_REQUESTER_EMAIL) |
        .tenant_request_ticket = strenv(INPUT_REQUEST_ID) |
        .siglum = strenv(INPUT_SIGLUM) |
        .cost_center = strenv(INPUT_COST_CENTER) |
        .requested_timestamp = strenv(REQUESTED_TIMESTAMP) |
        .provision_timestamp = strenv(PROVISION_TIMESTAMP) |
        .gpu_enabled = strenv(INPUT_GPU_ENABLED) |
        with(select(strenv(INPUT_GPU_ENABLED) == "true"); .gpu_tier = strenv(INPUT_GPU_TIER)) |
        .active_namespaces = [] |
        .active_sub_tenants = [] |
        .active_cso = []
      ' > "$TENANT_METADATA_FILE"
    fi

    SUB_EXISTS=$(yq e ".active_sub_tenants[] | select(.name == \"$TENANT_PROJECT\") | .name" "$TENANT_METADATA_FILE" 2>/dev/null)
    
    if [ -z "$SUB_EXISTS" ]; then
        # NEW SUB TENANT: Append to array
        log_info "Appending new Sub Tenant to metadata..."
        if [[ "$INPUT_LIFECYCLE" == "prod" ]]; then
            yq e -i '
                .active_sub_tenants += [{
                "name": strenv(TENANT_PROJECT),
                "requester": strenv(INPUT_REQUESTER_EMAIL),
                "namespace_request_ticket": strenv(INPUT_REQUEST_ID),
                "requested_timestamp": strenv(REQUESTED_TIMESTAMP),
                "provision_timestamp": strenv(PROVISION_TIMESTAMP),
                "lifecycle": strenv(INPUT_LIFECYCLE),
                "ard": strenv(INPUT_ARD_LINK)
                }]
            ' "$TENANT_METADATA_FILE"
        else
            yq e -i '
                .active_sub_tenants += [{
                "name": strenv(TENANT_PROJECT),
                "requester": strenv(INPUT_REQUESTER_EMAIL),
                "namespace_request_ticket": strenv(INPUT_REQUEST_ID),
                "requested_timestamp": strenv(REQUESTED_TIMESTAMP),
                "provision_timestamp": strenv(PROVISION_TIMESTAMP),
                "lifecycle": strenv(INPUT_LIFECYCLE)
                }]
            ' "$TENANT_METADATA_FILE"
        fi
    else
        # EXISTING NAMESPACE: Update Audit Trail
        log_info "Sub tenant $TENANT_PROJECT already in metadata. Appending to update history..."
        yq e -i '
            (.active_sub_tenants[] | select(.name == strenv(TENANT_PROJECT))).update_history += [{
            "update_ticket": strenv(INPUT_REQUEST_ID),
            "updated_timestamp": strenv(PROVISION_TIMESTAMP)
            }]
        ' "$TENANT_METADATA_FILE"
    fi

    # HANDLE ROUTE SECURITY EXCEPTION
    if [[ "$INPUT_ROUTE_EXCEPTION" == "true" ]]; then
        log_info "Adding Route security exception to metadata..."
        yq e -i '
          (.active_sub_tenants[] | select(.name == strenv(TENANT_PROJECT))).security_exception = {
            "request_ticket": strenv(INPUT_REQUEST_ID),
            "granted_at": strenv(EXCEPTION_GRANTED_DATE),
            "expires_at": strenv(EXCEPTION_EXPIRES_DATE)
          }
        ' "$TENANT_METADATA_FILE"
    fi

    log_info "Metadata updated."
}

function run_scaffold_project() {
    echo "==========================================================================="
    echo "                  Project Scaffolding - Directory Update                   "
    echo "==========================================================================="
    log_info "Creating directories..."

    mkdir -p "$PROJECT_DIR/docs"
    mkdir -p "$PROJECT_DIR/templates"

    if [ "$IS_EXISTING_PROJECT" == "false" ]; then
        log_info "Generating Project Files from templates..."
        cp "${TEMPLATE_DIR}/capsule/values.yaml.tpl" "$VALUES_FILE"

        # Replacements (Only needed on first creation) 
        sed -i "s|__TENANT_NAME__|${TENANT_NAME}|g" "$VALUES_FILE"
        sed -i "s|__TENANT_PROJECT__|${TENANT_PROJECT}|g" "$VALUES_FILE"
        sed -i "s|__TARGET_CLUSTER__|${INPUT_TARGET_CLUSTER}|g" "$VALUES_FILE"
        sed -i "s|__LIFECYCLE__|${INPUT_LIFECYCLE}|g" "$VALUES_FILE"
        sed -i "s|__SIGLUM__|${INPUT_SIGLUM}|g" "$VALUES_FILE"
        sed -i "s|__COST_CENTER__|${COST_CENTER_LABEL_VALUE}|g" "$VALUES_FILE"
        sed -i "s|__CONTACT_PERSON__|${INPUT_REQUESTER_EMAIL}|g" "$VALUES_FILE"
        sed -i "s|__REQUESTER_EMAIL__|${INPUT_REQUESTER_EMAIL}|g" "$VALUES_FILE"
        sed -i "s|__APP_LABEL__|${TENANT_PROJECT#dcsc-}|g" "$VALUES_FILE"

        cp "${TEMPLATE_DIR}/capsule/Chart.yaml.tpl" "$CHART_FILE"

        sed -i "s|__HARBOR_URL__|${HARBOR_LOCAL_URL}|g" "$CHART_FILE"
        sed -i "s|__HARBOR_OCI_PROJECT__|${HARBOR_OCI_PROJECT}|g" "$CHART_FILE"

        cp "${TEMPLATE_DIR}/helmignore.tpl" "$HELMIGNORE_FILE"
    else
        log_info "Existing project detected. Skipping template generation to preserve custom values."
    fi

    # =========================================================================
    # DYNAMIC UPDATES (Applies to BOTH New and Existing Projects)
    # =========================================================================

    # --- GPU Configuration Logic ---
    if [[ "$INPUT_GPU_ENABLED" == "true" && "$INPUT_GPU_TIER" != "NONE" ]]; then
        log_info "Configuring GPU resources for tier: $INPUT_GPU_TIER"
        export GPU_TPL_PATH="${TEMPLATE_DIR}/capsule/values-gpuconfig.yaml.tpl"
        yq eval -i '. *= load(strenv(GPU_TPL_PATH)).[strenv(INPUT_GPU_TIER)]' "$VALUES_FILE"
    fi

    # Inject route exception settings into values.yaml
    if [[ "$INPUT_ROUTE_EXCEPTION" == "true" ]]; then
        log_info "Updating Route Exception configurations in values.yaml..."
        yq e -i '
          .["dcs-tenant-provisioner"].routeException.enabled = true |
          .["dcs-tenant-provisioner"].routeException.requestId = strenv(INPUT_REQUEST_ID) |
          .["dcs-tenant-provisioner"].routeException.grantedAt = strenv(EXCEPTION_GRANTED_DATE)
        ' "$VALUES_FILE"
    fi

    echo "---------------------------------------------------------------------------"
    echo "                             Project Details                               "
    echo "---------------------------------------------------------------------------"
    echo "Customer/Tenant:                        $TENANT_NAME"
    echo "Sub Tenant:                             $TENANT_PROJECT"
    echo "Cluster:                                $INPUT_TARGET_CLUSTER"
    echo "Lifecycle:                              $INPUT_LIFECYCLE"
    echo "Route Exception:                        $INPUT_ROUTE_EXCEPTION"
    echo "Siglum:                                 $INPUT_SIGLUM"
    echo "Cost Center:                            $INPUT_COST_CENTER"
    echo "Req Time:                               $REQUESTED_TIMESTAMP"
    echo "Prov Time:                              $PROVISION_TIMESTAMP"
    echo "GPU Enabled:                            $INPUT_GPU_ENABLED"
    echo "---------------------------------------------------------------------------"
    echo "                             Project Paths                                 "
    echo "---------------------------------------------------------------------------"
    echo "Project Directory:                      $PROJECT_DIR"
    echo "Project Values File:                    $VALUES_FILE"
    echo "Project Chart File:                     $CHART_FILE"
    echo "Project Helmignore File:                $HELMIGNORE_FILE"
    echo "Tenant Metadata File:                   $TENANT_METADATA_FILE"
    echo "---------------------------------------------------------------------------"
}

function validate_security_policies() {
    echo "==========================================================================="
    echo "                         Security Policy Check                             "
    echo "==========================================================================="

    local TARGET_FILE="${VALUES_FILE}"
    
    log_info "Checking security compliance for $INPUT_LIFECYCLE..."
    log_info "Target file: $TARGET_FILE"
    if [[ "$INPUT_LIFECYCLE" == "prod" ]]; then
        if [[ ! -f "$TARGET_FILE" ]]; then
            log_error "CRITICAL: $TARGET_FILE does not exist. Cannot validate security."
            exit 1
        fi
        
        echo "------------------------------------------------------------"
        set +e
        INVALID_PUSH_FOUND=$(yq -e '."dcs-tenant-provisioner".harborRobotAccounts.robotAccounts[] | select(.default == false) | .permissions[] | select(.action == "push")' "$TARGET_FILE" 2>/dev/null)
        set -e

        if [[ -n "$INVALID_PUSH_FOUND" ]]; then
            echo "============================================================"
            echo "🚨 SECURITY VIOLATION: FORBIDDEN PUSH PERMISSIONS IN PROD 🚨"
            echo "============================================================"
            echo "File: $TARGET_FILE"
            echo ""

            grep -n -B 1 -E "action: [\"']?push[\"']?" "$TARGET_FILE" | grep -v "^--"     
            
            echo ""
            echo "============================================================"
            log_error "Custom Robot Accounts in PROD are NOT allowed to have 'push' permissions."
            log_error "Please remove these actions from your $VALUES_FILE."
            exit 1
        fi
        log_info "Security check passed: No unauthorized push permissions found for PROD."
    else
        log_info "Skipping push-restriction check (Lifecycle is $INPUT_LIFECYCLE)."
    fi
}

function run_git_ops() {
    log_info "Checking for actual configuration changes..."
    
    cd "$CLONE_DIR"
    # 1. Build the list of paths to check
    local CHECK_PATHS="$CUSTOMER_DIR"
    if [ -f "$IPPOOL_FILE" ]; then
        CHECK_PATHS="$CHECK_PATHS $IPPOOL_FILE"
    fi

    # 2. Check git status. We grep -v (exclude) the metadata file from the diff.
    # If the output is empty, it means no real files were modified.
    local CHANGES
    CHANGES=$(git status --porcelain $CHECK_PATHS | grep -v "/tenant-metadata.yaml$" || true)

    if [ -z "$CHANGES" ]; then
        echo "==========================================================================="
        log_error "No actual configuration changes detected for $TENANT_PROJECT."
        log_error "Pipeline run aborted to avoid creating empty Merge Requests."
        echo "==========================================================================="
        exit 1
    fi

    # 3. Proceed with Git operations since real changes exist
    log_info "Changes detected. Committing..."
    git config --global user.email "${GITLAB_USER_EMAIL}"
    git config --global user.name "${GITLAB_USER_NAME}"
    git checkout -b "$NEW_BRANCH_NAME"
    
    git add "$CUSTOMER_DIR"
    
    if [ -f "$IPPOOL_FILE" ]; then
        git add "$IPPOOL_FILE"
    fi
    
    git commit -m "feat: Scaffold/Update project $TENANT_PROJECT for customer $TENANT_NAME"
    git push origin "$NEW_BRANCH_NAME"    
    echo ""
    log_info " A new branch '$NEW_BRANCH_NAME' has been pushed."
    echo ""
    echo "---------------------------------------------------------------------------"
    echo "| **  Please create a Merge Request from this branch to continue.   **    |"
    echo "---------------------------------------------------------------------------"
}

# --- Main Execution Flow ---
if [[ "${DEBUG}" == "true" ]]; then
    echo "==========================================================================="
    echo "                         *** Debug Enabled ***                             "
    echo "==========================================================================="
    set -x
fi

enable_debug_if_requested

prepare_variables
sanity_checks
update_metadata
run_scaffold_project
validate_security_policies

run_git_ops
