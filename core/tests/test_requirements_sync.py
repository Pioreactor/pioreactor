# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
from pathlib import Path


def parse_setup_list(path: Path, name: str) -> list[str]:
    """Return list assigned to ``name`` in ``setup.py``."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return [ast.literal_eval(elt) for elt in node.value.elts]  # type: ignore
        elif isinstance(node, ast.AnnAssign):
            # variable with type annotation
            t = node.target
            if isinstance(t, ast.Name) and t.id == name:
                return [ast.literal_eval(elt) for elt in node.value.elts]  # type: ignore
    raise AssertionError(f"{name} not found")


def parse_requirements(path: Path) -> list[str]:
    """Parse a requirements file, resolving ``-r`` inclusions."""
    requirements: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            nested = (path.parent / line.split(maxsplit=1)[1]).resolve()
            requirements.extend(parse_requirements(nested))
        else:
            requirements.append(line)
    return requirements


def test_requirements_files_match_setup_py() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    req_dir = repo_root / "requirements"
    setup_py_path = repo_root / "core" / "setup.py"

    core = parse_setup_list(setup_py_path, "CORE_REQUIREMENTS")
    worker = parse_setup_list(setup_py_path, "WORKER_REQUIREMENTS")
    leader = parse_setup_list(setup_py_path, "LEADER_REQUIREMENTS")

    assert set(parse_requirements(req_dir / "requirements.txt")) == set(core)
    assert set(parse_requirements(req_dir / "requirements_worker.txt")) == set(core + worker)
    assert set(parse_requirements(req_dir / "requirements_leader.txt")) == set(core + leader)
    assert set(parse_requirements(req_dir / "requirements_leader_worker.txt")) == set(core + worker + leader)
