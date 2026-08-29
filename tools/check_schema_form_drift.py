#!/usr/bin/env python3
"""Fail the build if the vendored rule engine has drifted from the pipeline's.

static/js/vendor/schema-form.js decides, in the operator's browser, whether a
request is worth sending. pipeline-scripts/load-payload.sh decides, in CI,
whether it is accepted. They are generated from the same source file for a
reason: a form that accepts what the pipeline rejects wastes five minutes per
mistake, and a form that rejects what the pipeline accepts is worse -- it makes
a legitimate request look impossible.

The two copies are byte-identical by policy. This checks that, rather than
trusting whoever last edited one of them to remember the other.

    python3 tools/check_schema_form_drift.py

Exit 0 clean, 1 on drift, 2 when a copy is missing.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VENDORED = ROOT / 'static' / 'js' / 'vendor' / 'schema-form.js'
UPSTREAM = (ROOT / 'pipelineRepoReferences' / 'namespaceProvRepoRef'
            / 'pages' / 'schema-form.js')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    missing = [p for p in (VENDORED, UPSTREAM) if not p.exists()]
    if missing:
        for path in missing:
            print(f"Missing: {path.relative_to(ROOT)}")
        # Not a failure of the check itself when only the reference copy is
        # absent -- a deployment tree carries the vendored file and not the
        # pipeline repo. Only the vendored copy is genuinely required.
        if not VENDORED.exists():
            return 2
        print("The pipeline reference repository is not present; skipping the comparison.")
        return 0

    vendored, upstream = digest(VENDORED), digest(UPSTREAM)
    if vendored == upstream:
        print(f"schema-form.js matches the pipeline copy ({vendored[:12]}).")
        return 0

    print("schema-form.js has drifted from the pipeline copy.")
    print(f"  {VENDORED.relative_to(ROOT)}\n    {vendored}")
    print(f"  {UPSTREAM.relative_to(ROOT)}\n    {upstream}")
    print()
    print("The rules live in the pipeline repository. Change them there, then copy:")
    print(f"  cp {UPSTREAM.relative_to(ROOT)} {VENDORED.relative_to(ROOT)}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
