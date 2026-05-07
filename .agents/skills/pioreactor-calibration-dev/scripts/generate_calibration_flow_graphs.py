#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import ast
import importlib.util
import inspect
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pioreactor.calibrations.registry import get_protocol
from pioreactor.calibrations.session_flow import StepRegistry


@dataclass
class FlowGraph:
    name: str
    nodes: set[str]
    edges: set[tuple[str, str]]


def _iter_returned_class_names(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                yield node.value.func.id


def _has_ctx_complete_call(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "complete":
                return True
    return False


def _build_flow_graph(name: str, registry: StepRegistry) -> FlowGraph:
    class_name_to_step_id = {step_class.__name__: step_id for step_id, step_class in registry.items()}
    nodes = set(registry.keys())
    edges: set[tuple[str, str]] = set()

    for step_id, step_class in registry.items():
        source = textwrap.dedent(inspect.getsource(step_class.advance))
        tree = ast.parse(source)
        for class_name in _iter_returned_class_names(tree):
            target = class_name_to_step_id.get(class_name)
            if target:
                edges.add((step_id, target))
        if _has_ctx_complete_call(tree):
            nodes.add("complete")
            edges.add((step_id, "complete"))

    return FlowGraph(name=name, nodes=nodes, edges=edges)


def _dot_escape(value: str) -> str:
    return value.replace('"', '\\"')


def _write_dot(graph: FlowGraph, path: Path) -> None:
    lines = ["digraph calibration_flow {"]
    lines.append("  rankdir=LR;")
    lines.append("  node [shape=box, fontname=Helvetica];")
    for node in sorted(graph.nodes):
        lines.append(f'  {node} [label="{_dot_escape(node)}"]; ')
    for source, target in sorted(graph.edges):
        lines.append(f"  {source} -> {target};")
    lines.append("}")
    path.write_text("\n".join(lines))


def _sanitize_mermaid_id(value: str) -> str:
    return "node_" + "".join(ch if ch.isalnum() else "_" for ch in value)


def _write_mermaid(graph: FlowGraph, path: Path) -> None:
    id_map = {node: _sanitize_mermaid_id(node) for node in graph.nodes}
    lines = ["flowchart LR"]
    for node in sorted(graph.nodes):
        node_id = id_map[node]
        lines.append(f'  {node_id}["{node}"]')
    for source, target in sorted(graph.edges):
        lines.append(f"  {id_map[source]} --> {id_map[target]}")
    path.write_text("\n".join(lines))


def _render_png(dot_path: Path, png_path: Path) -> None:
    subprocess.run(
        ["dot", "-Tpng", str(dot_path), "-o", str(png_path)],
        check=True,
    )


def _load_plugin(plugin_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load plugin from {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate calibration flow graphs.")
    parser.add_argument("--protocol-name", required=True, help="Protocol name, e.g. 'duration_based'.")
    parser.add_argument("--target-device", required=True, help="Target device, e.g. 'stirring' or 'od'.")
    parser.add_argument(
        "--plugin-path",
        type=Path,
        help="Optional plugin file to load before resolving the protocol.",
    )
    parser.add_argument(
        "--format",
        choices=["dot", "mermaid", "both"],
        default="dot",
        help="Output format.",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Also render a PNG using graphviz dot (requires dot on PATH).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("scratch"),
        help="Directory to write output files.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.plugin_path is not None:
        _load_plugin(args.plugin_path)

    protocol = get_protocol(args.target_device, args.protocol_name)
    step_registry = getattr(protocol, "step_registry", None)
    if step_registry is None:
        raise SystemExit("Protocol does not define a step registry.")

    graph = _build_flow_graph(args.protocol_name, step_registry)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.format in {"dot", "both"}:
        dot_path = output_dir / f"{args.protocol_name}_flow.dot"
        _write_dot(graph, dot_path)
        print(f"Wrote {dot_path}")
        if args.png:
            png_path = output_dir / f"{args.protocol_name}_flow.png"
            _render_png(dot_path, png_path)
            print(f"Wrote {png_path}")

    if args.format in {"mermaid", "both"}:
        mermaid_path = output_dir / f"{args.protocol_name}_flow.mmd"
        _write_mermaid(graph, mermaid_path)
        print(f"Wrote {mermaid_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
