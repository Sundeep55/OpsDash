#!/bin/bash
# =============================================================================
# test-cases.sh — run tools/cases.json through the shell shim.
#
#   ./tools/test-cases.sh
#
# Checks three things per case, whichever the case declares:
#   expect    accept or reject
#   message   a substring the rejection must mention
#   exports   INPUT_* values the scripts would end up reading
#
# pages/parity.html runs the same file through the browser engine and must reach
# the same accept/reject verdict. Two engines enforcing one rule set is the whole
# design; one case file is how they stay honest about it.
# =============================================================================

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
export REQUEST_SCHEMA="${ROOT}/request-schema.yaml"
SHIM="${ROOT}/pipeline-scripts/load-payload.sh"
CASES="${HERE}/cases.json"

command -v yq >/dev/null 2>&1 || { echo "yq is not on PATH."; exit 1; }

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf "  ok    %s\n" "$1"; }
bad() { FAIL=$((FAIL+1)); printf "  FAIL  %s\n        %s\n" "$1" "$2"; }

echo "==========================================================================="
echo "                        load-payload.sh — tools/cases.json                 "
echo "==========================================================================="

COUNT=$(yq -p json -o json -r '.cases | length' "$CASES")
i=0
while [ "$i" -lt "$COUNT" ]; do
    NAME=$(yq   -p json -o json -r ".cases[$i].name" "$CASES")
    OP=$(yq     -p json -o json -r ".cases[$i].operation" "$CASES")
    EXPECT=$(yq -p json -o json -r ".cases[$i].expect" "$CASES")
    MSG=$(yq    -p json -o json -r ".cases[$i].message // \"\"" "$CASES")
    RAW=$(yq    -p json -o json -r ".cases[$i].raw_payload // \"\"" "$CASES")

    if [ -n "$RAW" ]; then
        PAYLOAD="$RAW"
    else
        PAYLOAD=$(yq -p json -o json -I=0 -r ".cases[$i].payload" "$CASES")
    fi

    OUT=$( export OPERATION="$OP" REQUEST_PAYLOAD="$PAYLOAD"
           # shellcheck disable=SC1090
           source "$SHIM" 2>&1
           env | grep '^INPUT_' | sort )
    STATUS=$?
    [ "$STATUS" -eq 0 ] && ACTUAL="accept" || ACTUAL="reject"

    if [ "$ACTUAL" != "$EXPECT" ]; then
        bad "$NAME" "expected $EXPECT, got $ACTUAL: $(printf '%s' "$OUT" | grep '^ERROR' | head -1)"
    elif [ "$ACTUAL" = "reject" ] && [ -n "$MSG" ] && ! printf '%s' "$OUT" | grep -qi -- "$MSG"; then
        bad "$NAME" "rejected, but not for '$MSG': $(printf '%s' "$OUT" | grep '^ERROR' | head -1)"
    else
        # Export assertions, when the case declares any.
        MISMATCH=""
        NKEYS=$(yq -p json -o json -r ".cases[$i].exports // {} | keys | length" "$CASES")
        k=0
        while [ "$k" -lt "$NKEYS" ]; do
            VAR=$(yq  -p json -o json -r ".cases[$i].exports | keys | .[$k]" "$CASES")
            WANT=$(yq -p json -o json -r ".cases[$i].exports[\"$VAR\"]" "$CASES")
            GOT=$(printf '%s\n' "$OUT" | grep "^${VAR}=" | head -1 | cut -d= -f2-)
            [ "$GOT" = "$WANT" ] || MISMATCH="${MISMATCH}${VAR}: expected '${WANT}', got '${GOT}'. "
            k=$((k + 1))
        done
        if [ -n "$MISMATCH" ]; then bad "$NAME" "$MISMATCH"; else ok "$NAME"; fi
    fi
    i=$((i + 1))
done

echo "==========================================================================="
printf "  %d passed, %d failed\n" "$PASS" "$FAIL"
echo "==========================================================================="
[ "$FAIL" -eq 0 ]
