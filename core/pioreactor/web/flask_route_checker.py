# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import os
import re
import sys

ROUTE_DECORATOR_NAMES = {"route", "add_url_rule"}
ROUTE_ARG_PATTERN = re.compile(r"<(\w+)>")


def extract_placeholders(route_string):
    return list(ROUTE_ARG_PATTERN.findall(route_string))


class RouteParamChecker(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.mismatches = []

    def visit_FunctionDef(self, node):
        route_placeholders = list()
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                if deco.func.attr in ROUTE_DECORATOR_NAMES:
                    if deco.args and isinstance(deco.args[0], ast.Constant):
                        route = deco.args[0].value
                        route_placeholders.extend(extract_placeholders(route))
        if route_placeholders:
            func_args = [arg.arg for arg in node.args.args]
            extra = set(route_placeholders) - set(func_args)
            missing = set(func_args) - set(route_placeholders)
            order = any(x != y for (x, y) in zip(route_placeholders, func_args))
            if extra or missing or order:
                self.mismatches.append(
                    {
                        "line": node.lineno,
                        "function": node.name,
                        "route_placeholders": route_placeholders,
                        "function_args": func_args,
                        "extra_placeholders": extra,
                        "missing_args": missing,
                        "order": order,
                    }
                )
        self.generic_visit(node)


def check_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=filepath)
    checker = RouteParamChecker(filepath)
    checker.visit(tree)
    return checker.mismatches


def main(directory):
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.endswith(".py"):
                path = os.path.join(root, fname)
                mismatches = check_file(path)
                for m in mismatches:
                    print(f"{path}:{m['line']} → function '{m['function']}'")
                    if m["extra_placeholders"]:
                        print(f"  Placeholders not in function signature: {sorted(m['extra_placeholders'])}")
                    if m["missing_args"]:
                        print(f"  Parameters not in route pattern: {sorted(m['missing_args'])}")
                    print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python flask_route_checker.py <path_to_your_flask_app_directory>")
        sys.exit(1)
    main(sys.argv[1])
