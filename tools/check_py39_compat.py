#!/usr/bin/env python3
"""Fail if the source uses syntax that Python 3.9 cannot run.

The development boxes run Python 3.9. The trap that motivated this: a PEP 604
union in an annotation --

    namespace_name: str | None

-- *parses* on 3.9, so `python -m compileall` and every linter pass. It only
raises at import time, when the annotation is evaluated:

    TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'

which surfaced as a crash on `runserver` with a traceback pointing at a
dataclass, not at anything obviously version-related. Use typing.Optional and
typing.Union instead.

Catching it needs the AST rather than a compile: this walks annotation
positions specifically, so `a | b` in ordinary expressions (a legitimate set or
int operation) is not flagged.

    python3 tools/check_py39_compat.py [paths...]

Exit 0 clean, 1 on findings. Runs on any Python 3.8+, so it does not need a 3.9
interpreter to be useful in CI.
"""
import ast
import pathlib
import sys

DEFAULT_PATHS = ['dashboard', 'ops_portal', 'tools', 'bin', 'manage.py']

# (attribute holding the annotation, node types that carry one)
ANNOTATED_NODES = (ast.AnnAssign, ast.arg, ast.FunctionDef, ast.AsyncFunctionDef)


def annotations_in(tree):
    """Yield every annotation expression, with the line it sits on."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and node.annotation:
            yield node.annotation
        elif isinstance(node, ast.arg) and node.annotation:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            yield node.returns


def uses_pep604(annotation):
    """True if the annotation contains a `X | Y` union at any depth."""
    for node in ast.walk(annotation):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return True
    return False


def check_file(path):
    findings = []
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except SyntaxError as exc:
        # Genuinely un-parseable on this interpreter; report rather than skip.
        return [(exc.lineno or 0, f'syntax error: {exc.msg}')]

    for annotation in annotations_in(tree):
        if uses_pep604(annotation):
            findings.append((
                annotation.lineno,
                'PEP 604 union in an annotation (`X | Y`); use typing.Optional/Union',
            ))
    return findings


def iter_python_files(paths):
    for raw in paths:
        path = pathlib.Path(raw)
        if path.is_dir():
            for found in sorted(path.rglob('*.py')):
                if '__pycache__' not in found.parts:
                    yield found
        elif path.suffix == '.py':
            yield path


def main(argv):
    paths = argv[1:] or DEFAULT_PATHS
    total = 0

    for path in iter_python_files(paths):
        for line, message in check_file(path):
            print(f"{path}:{line}: {message}")
            total += 1

    if total:
        print(f"\n{total} Python 3.9 incompatibility(ies). "
              f"These import cleanly on 3.10+ and fail at runtime on 3.9.",
              file=sys.stderr)
        return 1

    print("Python 3.9 compatible.")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
