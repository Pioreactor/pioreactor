# -*- coding: utf-8 -*-
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


def parse_setup_extras(path: Path) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "setup":
            continue
        for keyword in node.keywords:
            if keyword.arg == "extras_require":
                assert isinstance(keyword.value, ast.Dict)
                extras: dict[str, list[str]] = {}
                for key, value in zip(keyword.value.keys, keyword.value.values):
                    assert isinstance(key, ast.Constant)
                    assert isinstance(key.value, str)
                    if isinstance(value, ast.Name):
                        extras[key.value] = parse_setup_list(path, value.id)
                    elif isinstance(value, ast.BinOp):
                        assert isinstance(value.op, ast.Add)
                        assert isinstance(value.left, ast.Name)
                        assert isinstance(value.right, ast.Name)
                        extras[key.value] = parse_setup_list(path, value.left.id) + parse_setup_list(
                            path, value.right.id
                        )
                    else:
                        raise AssertionError(f"Unsupported extra value for {key.value}")
                return extras
    raise AssertionError("extras_require not found")


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


def test_setup_py_leader_extra_is_leader_only() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    setup_py_path = repo_root / "core" / "setup.py"

    worker = parse_setup_list(setup_py_path, "WORKER_REQUIREMENTS")
    leader = parse_setup_list(setup_py_path, "LEADER_REQUIREMENTS")
    extras = parse_setup_extras(setup_py_path)

    assert set(extras["leader"]) == set(leader)
    assert set(extras["leader"]).isdisjoint(worker)
    assert set(extras["leader_worker"]) == set(leader + worker)
