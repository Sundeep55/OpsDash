#!/bin/bash
# =============================================================================
# validate-ip-allocation.sh — catch a double-allocated egress IP at merge time.
#
# THE RACE
# --------
# Allocating an egress IP is read-then-write across a merge request:
#
#   1. the pipeline branches from main
#   2. scaffold-namespace.sh reads egressip-pool.yaml, picks IPs whose status is
#      "available", and marks them allocated on the branch
#   3. a human reviews and merges, possibly days later
#
# Nothing holds a lock across those steps, and nothing can: the pipeline does not
# own the file between branching and merging. Two requests raised the same
# morning both read the same pool and can both take the same IP.
#
# Git catches the narrow case where both branches edit the same lines. It does
# not catch the general one -- a branch cut weeks ago whose IPs were since taken
# by a request that merged first, where the two edits sit far enough apart in the
# file to merge cleanly. The result is two namespaces holding one IP, which the
# pool file then reports as allocated exactly once.
#
# WHAT THIS DOES
# --------------
# Runs on the merge request. For every IP this branch newly marks allocated, it
# checks the target branch: if that IP is already allocated there to a different
# object, the branch is stale and the pipeline fails with the conflict named.
#
# It does not fix the race -- it makes it loud and unmergeable instead of silent.
# The remedy is to re-run the scaffold pipeline, which reads the pool afresh.
#
#   ./tools/validate-ip-allocation.sh [target-ref]
#
# Exit 0 clean, 1 on a conflict, 0 with a note when there is no pool file.
# =============================================================================
set -e

TARGET_REF="${1:-origin/${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-main}}"
FINDINGS=0

command -v yq >/dev/null 2>&1 || { echo "yq is not on PATH."; exit 1; }

echo "==========================================================================="
echo "                    EgressIP allocation conflict check                     "
echo "==========================================================================="
echo "Comparing against: $TARGET_REF"

# Every pool file the branch touched. Nothing to check if it touched none.
POOL_FILES=$(git diff --name-only "$TARGET_REF"...HEAD -- '*/egressip-pool.yaml' || true)

if [ -z "$POOL_FILES" ]; then
    echo ""
    echo "  No egressip-pool.yaml changed in this merge request. Nothing to check."
    echo "==========================================================================="
    exit 0
fi

for POOL in $POOL_FILES; do
    echo ""
    echo "-> $POOL"

    # The target's copy. A pool file added on this branch has no counterpart,
    # and nothing can conflict with a file that does not exist there yet.
    if ! git show "$TARGET_REF:$POOL" > /tmp/pool_target.yaml 2>/dev/null; then
        echo "   new on this branch; no target version to compare against"
        continue
    fi

    # Allocated on the branch: ip<TAB>object
    git show "HEAD:$POOL" > /tmp/pool_branch.yaml 2>/dev/null || cp "$POOL" /tmp/pool_branch.yaml

    BRANCH_ALLOC=$(yq -r '.[] | .ips[] | select(.status == "allocated") | .ip + "|" + (.object // "")' /tmp/pool_branch.yaml)

    while IFS='|' read -r IP OBJECT; do
        [ -n "$IP" ] || continue

        # What the target branch says about this IP right now.
        export TARGET_IP="$IP"
        TARGET_STATUS=$(yq -r '.[] | .ips[] | select(.ip == strenv(TARGET_IP)) | .status // ""' /tmp/pool_target.yaml)
        TARGET_OBJECT=$(yq -r '.[] | .ips[] | select(.ip == strenv(TARGET_IP)) | .object // ""' /tmp/pool_target.yaml)

        # Unchanged, or allocated to the same object on both sides: fine.
        [ "$TARGET_STATUS" != "allocated" ] && continue
        [ "$TARGET_OBJECT" = "$OBJECT" ] && continue

        echo ""
        echo "   CONFLICT: $IP"
        echo "     this branch allocates it to : ${OBJECT:-<unnamed>}"
        echo "     $TARGET_REF already has it as: ${TARGET_OBJECT:-<unnamed>}"
        FINDINGS=$((FINDINGS + 1))
    done <<< "$BRANCH_ALLOC"
done

echo ""
echo "==========================================================================="
if [ "$FINDINGS" -gt 0 ]; then
    echo "  $FINDINGS egress IP(s) already allocated on $TARGET_REF."
    echo ""
    echo "  This branch was cut before those allocations merged, so it is handing"
    echo "  out addresses that are no longer free. Re-run the scaffold pipeline"
    echo "  for this request: it reads the pool afresh and picks free addresses."
    echo "==========================================================================="
    exit 1
fi
echo "  No conflicting egress IP allocations."
echo "==========================================================================="
