#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


def is_none_annotation(annotation: ast.AST | None) -> bool:
    """Return True when the annotation explicitly spells out None."""
    if annotation is None:
        return False

    if isinstance(annotation, ast.Constant):
        return annotation.value is None or annotation.value == "None"

    if isinstance(annotation, ast.Name):
        return annotation.id == "None"

    return False


def iter_test_functions(tree: ast.AST) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            yield node


def missing_annotations(path: Path) -> list[tuple[int, str]]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        return [(exc.lineno or 0, f"syntax error: {exc.msg}")]

    return [
        (node.lineno, node.name) for node in iter_test_functions(tree) if not is_none_annotation(node.returns)
    ]


def main(argv: list[str]) -> int:
    failure_count = 0

    for filename in argv[1:]:
        path = Path(filename)
        if not path.suffix == ".py" or not path.exists():
            continue

        missing = missing_annotations(path)
        for lineno, name in missing:
            failure_count += 1
            print(f"{path}:{lineno} {name} is missing a '-> None' return annotation")

    if failure_count:
        print("Add explicit '-> None' annotations to all test functions.")
    return int(failure_count > 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
