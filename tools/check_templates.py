#!/usr/bin/env python3
"""Fail on Vue components placed where the HTML parser will move them.

The bug this exists for: a custom element written as a direct child of a table
section --

    <tbody>
      <table-skeleton v-if="loading"></table-skeleton>
      <tr v-else-if="!rows.length">...</tr>
    </tbody>

-- is legal-looking, serves fine, and is silently relocated by the browser.
Only `<tr>`, `<template>`, `<script>` and a few others may sit inside `<tbody>`;
anything else is *foster-parented* out and re-inserted immediately before the
`<table>`. The component and the `<tr v-else-if>` end up in different parents,
so the v-else-if loses its adjacent v-if and Vue aborts compiling the whole
template with `compiler-30`. The page renders blank.

It survives development because the development Vue build reports the failure
and carries on; the production build throws. So the symptom appears only after
DEBUG=False, which is usually the first deploy.

The fix is Vue's documented in-DOM workaround: host the component on a real
`<tr>`, which the parser leaves alone.

    <tr is="vue:table-skeleton" v-if="loading"></tr>

    python3 tools/check_templates.py [paths...]

Exit 0 clean, 1 on findings. Pure stdlib, no Node, no Django.
"""
import pathlib
import re
import sys
from html.parser import HTMLParser

DEFAULT_PATHS = ['dashboard/templates']

# Elements whose children the HTML parser restricts. A child not in the
# corresponding allow-list gets foster-parented out of the table.
TABLE_SECTIONS = {
    'table': {'caption', 'colgroup', 'col', 'thead', 'tbody', 'tfoot', 'tr', 'template', 'script', 'style'},
    'thead': {'tr', 'template', 'script', 'style'},
    'tbody': {'tr', 'template', 'script', 'style'},
    'tfoot': {'tr', 'template', 'script', 'style'},
    'tr': {'td', 'th', 'template', 'script', 'style'},
}

# Django template tags would confuse the HTML parser; strip them first.
DJANGO_TAG = re.compile(r'\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}', re.S)


class TablePlacementChecker(HTMLParser):
    """Reports custom elements sitting directly inside a table section."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.findings = []

    def handle_starttag(self, tag, attrs):
        parent = self.stack[-1] if self.stack else None
        allowed = TABLE_SECTIONS.get(parent)

        if allowed is not None and tag not in allowed:
            # `is="vue:x"` on a permitted tag is the correct form and is fine;
            # anything else here will be relocated by the parser.
            self.findings.append((
                self.getpos()[0],
                f'<{tag}> is not valid directly inside <{parent}>; the HTML parser '
                f'will move it out of the table. Use <tr is="vue:{tag}"> instead.',
            ))

        # Void elements never open a scope.
        if tag not in {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'path', 'circle', 'ellipse'}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        # Unwind to the matching open tag; templates are not always balanced
        # once Django tags have been stripped.
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass


def check_file(path):
    text = DJANGO_TAG.sub('', path.read_text(encoding='utf-8'))
    checker = TablePlacementChecker()
    try:
        checker.feed(text)
    except Exception as exc:  # a malformed fragment should not mask real findings
        return [(0, f'could not parse: {exc}')]
    return checker.findings


def main(argv):
    paths = argv[1:] or DEFAULT_PATHS
    total = 0

    for raw in paths:
        root = pathlib.Path(raw)
        files = sorted(root.rglob('*.html')) if root.is_dir() else [root]
        for path in files:
            for line, message in check_file(path):
                print(f"{path}:{line}: {message}")
                total += 1

    if total:
        print(f"\n{total} template placement problem(s). These serve fine and render "
              f"blank under the production Vue build.", file=sys.stderr)
        return 1

    print("Template component placement OK.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
