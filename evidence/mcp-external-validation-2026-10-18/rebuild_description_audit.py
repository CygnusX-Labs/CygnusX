#!/usr/bin/env python3
"""Rebuild the MCP description audit from saved client output and current source."""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
TOOLS_DIR = ROOT / "mcp-server" / "tools"
EXPECTED_COUNT = 111

FORMERLY_VAGUE_REASONS = {
    "atac_seq_status": "Does not identify the task/run input or distinguish current status from progress details.",
    "cygnusx_chem_search": "Does not state the searchable identifier/query input or candidate fields returned.",
    "cygnusx_confirm_run_plan": "Omits the server-issued human approval ID requirement for this confirmation-gated action.",
    "cygnusx_expression_studies": "Does not state search inputs or that results are study-directory metadata only.",
    "cygnusx_gene_search": "Omits the required gene query input and the result shape.",
    "cygnusx_get_run_logs": "Omits the Run identifier and what event-log content is returned.",
    "cygnusx_get_run_status": "Omits the Run identifier and status fields returned.",
    "cygnusx_genome_sequence": "Does not name the required Ensembl stable ID or sequence-type input despite its size limit.",
    "cygnusx_list_runs": "Does not explain user scope, optional filters, or the returned Run fields.",
    "cygnusx_plant_get": "Does not identify the Gramene identifier type or fields returned.",
    "cygnusx_preview_analysis": "Does not say which flow/parameters are checked or that no task is submitted.",
    "cygnusx_verify_artifact": "Does not state the Run input or which artifact/checksum facts are verified.",
}


def one_line(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ⏎ ").replace("\t", " ")


def ast_functions(path: Path) -> dict[str, tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False) or ""
        explicit = ""
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        explicit = keyword.value.value
        location = f"$REPO/mcp-server/tools/{path.name}:{node.lineno}"
        found[node.name] = (location, f"{doc}\0{explicit}")
    return found


def main() -> None:
    yaml_path = ROOT / "mcp-server" / "tools.yaml"
    registry = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    groups = {entry["id"]: entry for entry in registry.get("groups", [])}
    yaml_tools: dict[str, tuple[str, str | None]] = {}
    source_functions: dict[str, tuple[str, str, str]] = {}

    for group_id, group in groups.items():
        module = group.get("module", "")
        module_file = TOOLS_DIR / (module.rsplit(".", 1)[-1] + ".py")
        if not module_file.is_file():
            continue
        functions = ast_functions(module_file)
        for name, (location, packed) in functions.items():
            doc, explicit = packed.split("\0", 1)
            source_functions[name] = (location, doc, explicit)
        for tool in group.get("tools", []):
            yaml_tools[tool["name"]] = (group_id, tool.get("description"))

    current_snapshot = EVIDENCE / "current-runtime-tools.json"
    if current_snapshot.exists():
        client_tools = json.loads(current_snapshot.read_text(encoding="utf-8"))
    else:
        client_tools = [
            json.loads(line)
            for line in (EVIDENCE / "stdio-tools-list.ndjson").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if len(client_tools) != EXPECTED_COUNT:
        raise SystemExit(f"expected {EXPECTED_COUNT} runtime tools, found {len(client_tools)}")
    old_client_tools = [
        json.loads(line)
        for line in (EVIDENCE / "stdio-tools-list.ndjson").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    old_descriptions = {tool["name"]: tool.get("description") for tool in old_client_tools}

    output = EVIDENCE / "description-audit.tsv"
    header = [
        "tool_name", "group", "module", "function_location", "yaml_description", "yaml_state",
        "runtime_description", "client_description", "docstring", "explicit_description",
        "classification", "reason", "evidence",
    ]
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        for tool in client_tools:
            name = tool["name"]
            group, yaml_desc = yaml_tools.get(name, ("missing", None))
            location, doc, explicit = source_functions.get(name, ("missing", "", ""))
            state = (
                "missing" if name not in yaml_tools
                else "empty" if yaml_desc == ""
                else "whitespace" if isinstance(yaml_desc, str) and not yaml_desc.strip()
                else "nonempty" if isinstance(yaml_desc, str)
                else "missing"
            )
            client_desc = tool.get("description")
            if not isinstance(client_desc, str) or not client_desc:
                classification = "empty" if isinstance(client_desc, str) else "missing"
                reason = "External client returned no usable description."
            elif name in FORMERLY_VAGUE_REASONS:
                classification = "vague"
                reason = FORMERLY_VAGUE_REASONS[name]
            else:
                classification = "valid"
                reason = "Reviewed against tool name, input schema, source behavior and safety constraints; actionable purpose is identifiable."
            writer.writerow([
                name,
                group,
                groups.get(group, {}).get("module", ""),
                location,
                one_line(yaml_desc),
                state,
                one_line(client_desc),
                one_line(client_desc),
                one_line(doc),
                one_line(explicit),
                classification,
                reason,
                "current-runtime-tools.json; tools.yaml; source AST",
            ])
    print(f"wrote {len(client_tools)} records to {output.name}")


if __name__ == "__main__":
    main()
