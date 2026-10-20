#!/usr/bin/env python3
"""Check memory defaults without importing Settings or reading the real .env."""

from __future__ import annotations

import argparse
import ast
import math
import sys
from pathlib import Path

_MEMORY_PREFIXES = ("MEMORY_", "AGENT_MEMORY_")


def memory_defaults(source: str) -> dict[str, str | bool | int | float | None]:
    """Read literal Settings defaults, including Field(default=...), without execution."""
    tree = ast.parse(source)
    settings = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    defaults: dict[str, str | bool | int | float | None] = {}
    for node in settings.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        name = node.target.id.upper()
        if not name.startswith(_MEMORY_PREFIXES):
            continue
        value = node.value
        if isinstance(value, ast.Call):
            if not isinstance(value.func, ast.Name) or value.func.id != "Field":
                raise ValueError(f"{name}: unsupported default expression")
            value = next((item.value for item in value.keywords if item.arg == "default"), None)
        if value is None:
            raise ValueError(f"{name}: missing literal default")
        default = ast.literal_eval(value)
        if type(default) not in {str, bool, int, float, type(None)}:
            raise ValueError(f"{name}: unsupported default type")
        defaults[name] = default
    if not defaults:
        raise ValueError("No memory Settings fields found")
    return defaults


def _matches(value: str, default: str | bool | int | float | None) -> bool:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if default is None:
        return value == ""
    if isinstance(default, bool):
        return value.lower() == str(default).lower()
    if isinstance(default, str):
        return value == default
    try:
        number = float(value)
        return math.isfinite(number) and number == default
    except ValueError:
        return False


def check_drift(config_source: str, example_source: str) -> list[str]:
    """Return field names/reasons only; never include environment variable values."""
    defaults = memory_defaults(config_source)
    entries: dict[str, str] = {}
    issues: list[str] = []
    for line in example_source.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        # MEM0_* is a protected, unconsumed migration remnant, outside this check.
        if not separator or not name.startswith(_MEMORY_PREFIXES):
            continue
        if name in entries:
            issues.append(f"{name}: duplicate assignment")
        entries[name] = value.strip()
    for name in sorted(entries.keys() - defaults.keys()):
        issues.append(f"{name}: no matching Settings field (comment out unused examples)")
    for name, default in sorted(defaults.items()):
        if name not in entries:
            issues.append(f"{name}: missing example")
        elif not _matches(entries[name], default):
            issues.append(f"{name}: example differs from Settings default")
    return issues


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "src/cygnusx/core/config.py")
    parser.add_argument("--example", type=Path, default=root / ".env.example")
    args = parser.parse_args()
    try:
        issues = check_drift(args.config.read_text(), args.example.read_text())
    except (OSError, SyntaxError, ValueError, StopIteration):
        sys.stderr.write("Memory configuration drift check could not parse its inputs.\n")
        return 1
    for issue in issues:
        sys.stderr.write(issue + "\n")
    if issues:
        return 1
    sys.stdout.write("Memory environment examples match Settings defaults; MEM0_* excluded.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
