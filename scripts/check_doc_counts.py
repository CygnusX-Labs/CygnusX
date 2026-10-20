#!/usr/bin/env python3
"""校验文档中的当前事实计数与结构化事实源一致。

设计原则：
- 事实值优先从结构化来源解析（AST / YAML / 迁移目录 / 工具注册表）。
- 只校验显式登记的“当前事实”断言，不做全库数字正则替换。
- 带日期或标记为历史快照的段落不参与自动比对，列为人工复核项。
- 无法自动判定的语义事实输出人工审核项，不阻塞 CI。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"

MODELS_DIR = SRC_ROOT / "cygnusx/infrastructure/database/models"
MIGRATIONS_DIR = ROOT / "alembic/versions"
IMAGE_MAPPING = ROOT / "deploy/image-mapping.yaml"
TOOLS_SCHEMA = ROOT / "tool_configs/tools_schema.yaml"
TOOLS_SETTING = ROOT / "tool_configs/tools_setting.yaml"
STUDIO_TOOLS = SRC_ROOT / "cygnusx/application/services/studio_tools.py"
SECURITY_CHECKLIST = ROOT / "wiki/security/hardening-checklist.md"

CHECKBOX = re.compile(r"^\s*- \[[ xX]\]")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# 仅显式历史标记才把整个小节视为历史；"(as-built，2026-xx-xx)" 是当前文档状态，
# 不触发历史判定；"(2026-xx-xx as-built)" 是带日期的施工记录，触发。
SECTION_HISTORY = re.compile(
    r"(历史快照|历史记录|历史值|历史口径|施工记录|交接记录|验收记录|复盘|回顾"
    r"|[（(]\s*20\d{2}-\d{2}-\d{2}\s+as-built\s*[）)])"
)
LINE_HISTORY = re.compile(r"(历史快照|历史记录|历史值|历史口径|当时|^\s*(?:[->*]\s*)?20\d{2}-\d{2}-\d{2})")

SCAN_ROOTS = (ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "ARCHITECTURE_DESIGN", ROOT / "wiki")
SKIP_DIR_PARTS = {"deprecated", "node_modules", ".git"}
# 整体属于历史快照的文件：不参与“当前事实”扫描。
HISTORICAL_FILES = {
    ROOT / "ARCHITECTURE_DESIGN/ARCHITECTURE_DISCOVERY_REPORT.md",
    ROOT / "ARCHITECTURE_DESIGN/CygnusX_studio_handover.md",
}

# 非注册断言的广度扫描规则：只针对已登记的事实类别，命中不一致仅告警。
SCAN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("orm_tables", re.compile(r"(\d+)\s*张\s*ORM\s*(?:管理)?表")),
    ("model_modules", re.compile(r"(\d+)\s*个模型模块")),
    ("alembic_migrations", re.compile(r"(\d+)\s*个迁移")),
    ("images", re.compile(r"(\d+)\s*(?:个镜像|images)")),
    ("static_tools", re.compile(r"静态\s*(\d+)\s*个\s*LLM function")),
    ("studio_tools", re.compile(r"(\d+)\s*个工具名")),
    ("security_checks", re.compile(r"(\d+)\s*项已知风险")),
)

MANUAL_REVIEW = (
    "wiki/features/toolbox.md 的“约 19 个工具、6 个分组”：工具数与分组数由 tools_setting.yaml 核对，"
    "“约”的语义口径仍需人工确认。",
    "Agent execution_path 的“实际发射值 vs 规划值”属于语义判断，脚本不自动核对。",
    "Dataset 七张物理表、Handoff 为 DatasetVersion 内部契约（非独立表）属于 schema 语义，脚本不自动核对。",
)


@dataclass(frozen=True)
class Fact:
    key: str
    value: int
    source: str


@dataclass(frozen=True)
class Assertion:
    path: str
    pattern: str
    fact: str
    note: str = ""


@dataclass(frozen=True)
class Finding:
    level: str
    path: str
    line: int
    message: str


ASSERTIONS: tuple[Assertion, ...] = (
    Assertion("AGENTS.md", r"PostgreSQL\+pgvector（(\d+) 表）", "orm_tables", "数据库规模"),
    Assertion(
        "AGENTS.md",
        r"镜像清单唯一权威源（当前 (\d+) 个",
        "images",
        "镜像清单",
    ),
    Assertion("ARCHITECTURE_DESIGN/README.md", r"全量注册 (\d+) 表", "orm_tables"),
    Assertion("ARCHITECTURE_DESIGN/README.md", r"静态 (\d+) 个 LLM function", "static_tools"),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_database_architecture.md",
        r"(\d+) 张 ORM 表注册",
        "orm_tables",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_database_architecture.md",
        r"承载 (\d+) 张 ORM 管理表",
        "orm_tables",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_database_architecture.md",
        r"(\d+) 个模型模块",
        "model_modules",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_database_architecture.md",
        r"全量导入注册（(\d+) 表）",
        "orm_tables",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_database_architecture.md",
        r"alembic/\s+(\d+) 个迁移",
        "alembic_migrations",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_toolbox_architecture.md",
        r"前端卡片，(\d+) 个工具",
        "tools_setting_tools",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_toolbox_architecture.md",
        r"、(\d+) 个启用",
        "tools_setting_enabled",
    ),
    Assertion(
        "ARCHITECTURE_DESIGN/CygnusX_toolbox_architecture.md",
        r"静态 (\d+) 个 LLM function",
        "static_tools",
    ),
    Assertion("wiki/README.md", r"\| (\d+) 表、连接池", "orm_tables"),
    Assertion("wiki/architecture/index.md", r"(\d+) 张 ORM 表", "orm_tables"),
    Assertion("wiki/architecture/database.md", r"(\d+) 张 ORM 表", "orm_tables"),
    Assertion(
        "wiki/architecture/overview.md",
        r"当前 (\d+) 个，以清单与 `make validate-image-mapping`",
        "images",
    ),
    Assertion(
        "wiki/architecture/sandbox.md",
        r"当前 (\d+) 个，以 `make validate-image-mapping`",
        "images",
    ),
    Assertion("wiki/deployment/index.md", r"当前 (\d+) 个，以清单与校验命令", "images"),
    Assertion(
        "wiki/development/project-structure.md",
        r"当前 (\d+) 个，以清单与 `make validate-image-mapping`",
        "images",
    ),
    Assertion("wiki/features/toolbox.md", r"当前约 (\d+) 个工具", "tools_setting_tools"),
    Assertion("wiki/features/toolbox.md", r"、(\d+) 个分组", "tools_setting_groups"),
    Assertion("wiki/features/toolbox.md", r"静态 (\d+) 个 LLM function", "static_tools"),
    Assertion("wiki/architecture/agent-runtime.md", r"当前注册 (\d+) 个工具名", "studio_tools"),
    Assertion("wiki/security/index.md", r"(\d+) 项已知风险修复", "security_checks"),
)


def _read_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assignment(node: ast.stmt) -> tuple[list[ast.expr], ast.expr | None]:
    if isinstance(node, ast.Assign):
        return list(node.targets), node.value
    if isinstance(node, ast.AnnAssign):
        return [node.target], node.value
    return [], None


def _is_name(target: ast.expr, name: str) -> bool:
    return isinstance(target, ast.Name) and target.id == name


def count_orm_tables() -> int:
    names: set[str] = set()
    for path in sorted(MODELS_DIR.glob("*.py")):
        for node in ast.walk(_read_tree(path)):
            targets, value = _assignment(node) if isinstance(node, (ast.Assign, ast.AnnAssign)) else ([], None)
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            if any(_is_name(target, "__tablename__") for target in targets):
                names.add(value.value)
    return len(names)


def count_model_modules() -> int:
    return sum(1 for path in MODELS_DIR.glob("*.py") if path.name != "__init__.py")


def count_migrations() -> int:
    return sum(1 for path in MIGRATIONS_DIR.glob("*.py") if path.name != "__init__.py")


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层不是映射")
    return data


def _imported_symbols(tree: ast.Module) -> dict[str, tuple[str, str]]:
    symbols: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                symbols[alias.asname or alias.name] = (node.module, alias.name)
    return symbols


def _module_path(module: str) -> Path | None:
    package_path = SRC_ROOT / Path(*module.split("."))
    if package_path.with_suffix(".py").is_file():
        return package_path.with_suffix(".py")
    init_path = package_path / "__init__.py"
    return init_path if init_path.is_file() else None


def _resolve_symbol(
    name: str, module_path: Path, seen: set[tuple[Path, str]], original: str | None = None
) -> str | None:
    # original 保留被导入的原始符号名；name 是当前模块内的可见名。
    lookup = original or name
    key = (module_path, lookup)
    if key in seen:
        return None
    seen.add(key)

    tree = _read_tree(module_path)
    imports = _imported_symbols(tree)
    for node in tree.body:
        targets, value = _assignment(node)
        if not any(_is_name(target, lookup) for target in targets) or value is None:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        if isinstance(value, ast.Name):
            imported = imports.get(value.id)
            if imported is None:
                return None
            module, symbol = imported
            target_path = _module_path(module)
            if target_path is None:
                return None
            return _resolve_symbol(value.id, target_path, seen, original=symbol)
        return None

    imported = imports.get(lookup)
    if imported is None:
        return None
    module, symbol = imported
    target_path = _module_path(module)
    if target_path is None:
        return None
    return _resolve_symbol(symbol, target_path, seen)


def studio_tool_names() -> list[str]:
    tree = _read_tree(STUDIO_TOOLS)
    value: ast.expr | None = None
    for node in tree.body:
        targets, assigned = _assignment(node)
        if any(_is_name(target, "STUDIO_TOOL_NAMES") for target in targets):
            value = assigned
    if value is None:
        raise ValueError("未在 studio_tools.py 找到 STUDIO_TOOL_NAMES")
    if isinstance(value, ast.Call) and value.args:
        value = value.args[0]
    if not isinstance(value, (ast.Set, ast.List, ast.Tuple)):
        raise ValueError("STUDIO_TOOL_NAMES 不是可静态解析的集合字面量")

    names: list[str] = []
    seen: set[tuple[Path, str]] = set()
    for element in value.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            names.append(element.value)
        elif isinstance(element, ast.Name):
            resolved = _resolve_symbol(element.id, STUDIO_TOOLS, seen)
            if resolved is None:
                raise ValueError(f"无法解析 STUDIO_TOOL_NAMES 元素: {element.id}")
            names.append(resolved)
        else:
            raise ValueError(f"STUDIO_TOOL_NAMES 含无法静态解析的元素: {ast.dump(element)}")
    return names


def count_security_checks() -> int:
    return sum(
        1
        for line in SECURITY_CHECKLIST.read_text(encoding="utf-8").splitlines()
        if CHECKBOX.match(line)
    )


def collect_facts() -> dict[str, Fact]:
    images = _load_yaml(IMAGE_MAPPING).get("images") or {}
    static_tools = _load_yaml(TOOLS_SCHEMA).get("tools") or []
    setting_tools = _load_yaml(TOOLS_SETTING).get("tools") or []
    enabled_tools = [
        tool
        for tool in setting_tools
        if not isinstance(tool, dict) or tool.get("enabled", True) is not False
    ]
    groups = {
        tool.get("group")
        for tool in setting_tools
        if isinstance(tool, dict) and tool.get("group")
    }
    return {
        "orm_tables": Fact(
            "orm_tables", count_orm_tables(), "models/*.py 中 __tablename__ 的去重值"
        ),
        "model_modules": Fact(
            "model_modules", count_model_modules(), "models/*.py（不含 __init__.py）"
        ),
        "alembic_migrations": Fact(
            "alembic_migrations", count_migrations(), "alembic/versions/*.py（不含 __init__.py）"
        ),
        "images": Fact("images", len(images), "deploy/image-mapping.yaml:images"),
        "static_tools": Fact("static_tools", len(static_tools), "tool_configs/tools_schema.yaml:tools"),
        "tools_setting_tools": Fact(
            "tools_setting_tools", len(setting_tools), "tool_configs/tools_setting.yaml:tools"
        ),
        "tools_setting_enabled": Fact(
            "tools_setting_enabled", len(enabled_tools), "tools_setting.yaml enabled!=false"
        ),
        "tools_setting_groups": Fact(
            "tools_setting_groups", len(groups), "tools_setting.yaml tools[].group 去重"
        ),
        "studio_tools": Fact(
            "studio_tools", len(studio_tool_names()), "STUDIO_TOOL_NAMES（frozenset 元素）"
        ),
        "security_checks": Fact(
            "security_checks", count_security_checks(), "wiki/security/hardening-checklist.md 复选框"
        ),
    }


def _iter_markdown_lines(path: Path) -> Iterator[tuple[int, str, bool]]:
    """逐行返回 (行号, 内容, 是否处于历史段落)。"""
    levels: list[int] = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            yield lineno, line, False
            continue
        heading = None if in_fence else HEADING.match(line)
        if heading is not None:
            level = len(heading.group(1))
            while levels and levels[-1] >= level:
                levels.pop()
            if SECTION_HISTORY.search(heading.group(2)):
                levels.append(level)
        yield lineno, line, bool(levels) or bool(LINE_HISTORY.search(line))


def check_assertions(facts: dict[str, Fact]) -> list[Finding]:
    findings: list[Finding] = []
    for assertion in ASSERTIONS:
        path = ROOT / assertion.path
        text = path.read_text(encoding="utf-8")
        match = re.search(assertion.pattern, text)
        if match is None:
            findings.append(
                Finding(
                    "ERROR",
                    assertion.path,
                    0,
                    f"断言未命中（pattern={assertion.pattern!r}）；文档改写后请同步更新脚本注册表",
                )
            )
            continue
        line = text.count("\n", 0, match.start()) + 1
        actual = int(match.group(1))
        expected = facts[assertion.fact].value
        if actual != expected:
            findings.append(
                Finding(
                    "ERROR",
                    assertion.path,
                    line,
                    f"{assertion.fact} 文档写 {actual}，事实源为 {expected}"
                    + (f"（{assertion.note}）" if assertion.note else ""),
                )
            )
        else:
            findings.append(
                Finding("OK", assertion.path, line, f"{assertion.fact}={expected}")
            )
    return findings


def _should_scan(path: Path) -> bool:
    if path in HISTORICAL_FILES:
        return False
    return not any(part in SKIP_DIR_PARTS for part in path.parts)


def scan_documents(facts: dict[str, Fact]) -> list[Finding]:
    findings: list[Finding] = []
    paths: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            paths.append(root)
        else:
            paths.extend(sorted(root.rglob("*.md")))
    for path in paths:
        if not _should_scan(path):
            continue
        relative = path.relative_to(ROOT).as_posix()
        for lineno, line, historical in _iter_markdown_lines(path):
            for fact_key, rule in SCAN_RULES:
                for match in rule.finditer(line):
                    value = int(match.group(1))
                    expected = facts[fact_key].value
                    if historical:
                        findings.append(
                            Finding(
                                "HISTORICAL",
                                relative,
                                lineno,
                                f"{fact_key} 历史值 {value}（当前 {expected}，不参与比对）",
                            )
                        )
                    elif value != expected:
                        findings.append(
                            Finding(
                                "WARN",
                                relative,
                                lineno,
                                f"疑似当前事实漂移：{fact_key} 写 {value}，事实源为 {expected}；请人工确认",
                            )
                        )
    return findings


def _format_facts(facts: dict[str, Fact]) -> list[str]:
    return [f"  {fact.key:<20} {fact.value:>5}  <- {fact.source}" for fact in facts.values()]


def main() -> int:
    parser = argparse.ArgumentParser(description="校验文档当前事实计数与结构化事实源一致")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument(
        "--strict-scan", action="store_true", help="把非注册断言的扫描告警升级为失败"
    )
    args = parser.parse_args()

    try:
        facts = collect_facts()
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[FATAL] 事实源解析失败: {exc}", file=sys.stderr)
        return 2

    assertion_findings = check_assertions(facts)
    scan_findings = scan_documents(facts)
    errors = [finding for finding in assertion_findings if finding.level == "ERROR"]
    warnings = [finding for finding in scan_findings if finding.level == "WARN"]
    historical = [finding for finding in scan_findings if finding.level == "HISTORICAL"]
    failed = bool(errors) or (args.strict_scan and bool(warnings))

    if args.json:
        print(
            json.dumps(
                {
                    "facts": [asdict(fact) for fact in facts.values()],
                    "assertions": [asdict(finding) for finding in assertion_findings],
                    "scan": [asdict(finding) for finding in scan_findings],
                    "manual_review": list(MANUAL_REVIEW),
                    "result": "FAIL" if failed else "PASS",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if failed else 0

    print("结构化事实源：")
    print("\n".join(_format_facts(facts)))
    print("\n注册断言：")
    for finding in assertion_findings:
        location = f"{finding.path}:{finding.line}" if finding.line else finding.path
        print(f"  {finding.level:<4} {location}  {finding.message}")
    if warnings:
        print("\n扫描告警（非注册断言，需人工确认）：")
        for finding in warnings:
            print(f"  WARN {finding.path}:{finding.line}  {finding.message}")
    if historical:
        print("\n历史快照（识别后跳过自动比对）：")
        for finding in historical:
            print(f"  HIST {finding.path}:{finding.line}  {finding.message}")
    print("\n人工复核项：")
    for item in MANUAL_REVIEW:
        print(f"  - {item}")
    print(
        f"\n结果：{'FAIL' if failed else 'PASS'}"
        f"（{len(facts)} 类事实，{len(ASSERTIONS)} 条注册断言，"
        f"{len(warnings)} 条扫描告警）"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
