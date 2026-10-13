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
                    elif isinstance(value, ast.List):
                        extras[key.value] = [ast.literal_eval(elt) for elt in value.elts]
                    else:
                        raise AssertionError(f"Unsupported extra value for {key.value}")
                return extras
    raise AssertionError("extras_require not found")


def test_requirements_files_match_setup_py() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    req_dir = repo_root / "requirements"
    setup_py_path = repo_root / "core" / "setup.py"

    core = parse_setup_list(setup_py_path, "CORE_REQUIREMENTS")
    hardware = parse_setup_list(setup_py_path, "HARDWARE_REQUIREMENTS")

    assert set(parse_requirements(req_dir / "requirements.txt")) == set(core)
    assert set(parse_requirements(req_dir / "requirements_hardware.txt")) == set(core + hardware)


def test_setup_py_role_extras_are_aliases() -> None:
    # every unit can become a leader, so the only real extra is hardware; the role-named
    # extras stay for older images, installers and updates across releases.
    repo_root = Path(__file__).resolve().parent.parent.parent
    setup_py_path = repo_root / "core" / "setup.py"

    hardware = parse_setup_list(setup_py_path, "HARDWARE_REQUIREMENTS")
    extras = parse_setup_extras(setup_py_path)

    assert set(extras["hardware"]) == set(hardware)
    assert set(extras["worker"]) == set(hardware)
    assert set(extras["leader_worker"]) == set(hardware)
    assert extras["leader"] == []
