#!/usr/bin/env python3
"""存储路径守卫：禁止 src/ 内新增 /data/ 字面量绝对路径（存储层优化 Phase 3）。

运行方式：
    python scripts/check_storage_paths.py

规则：
1. src/cygnusx/**/*.py 中不得出现 "/data/..." 字面量（含 /data/cygnusx、
   /data/omichub 等），防止换根部署时再次产生"同进程两套数据根"的静默故障。
2. 白名单（豁免文件 + 豁免模式）：
   - core/config.py 与 infrastructure/config/storage_config.py：
     storage_path 默认值 / 兜底常量是全平台唯一锚点（容器内规范路径），
     其派生逻辑由单元测试守护；
   - 各工具 runner.py 的容器内挂载目标 ":/data/cygnusx"（Docker volume 声明
     的容器侧端点，容器内路径约定，与宿主根无关）；
   - 纯文档字符串 / 注释中说明"容器内固定为 /data/cygnusx"的表述。

退出码：发现违规 1，干净 0。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "cygnusx"

# /data/<segment> 形态的字面量（匹配字符串内出现的绝对路径）
_DATA_LITERAL_RE = re.compile(r"[\"']/data/[A-Za-z0-9_.\-]+")

# 文件级白名单：这些文件中的命中是"存储根锚点"或"容器内路径约定"，属合法
_FILE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "core/config.py",                       # storage_path 默认值 + 兜底（唯一锚点）
        "infrastructure/config/storage_config.py",  # _DEFAULT_DATA_ROOT 兜底常量
    }
)

# 行级白名单：这些模式命中的行是容器内挂载目标或文档说明，属合法
_LINE_ALLOWLIST: tuple[re.Pattern[str], ...] = (
    re.compile(r":/data/cygnusx"),              # Docker volume 容器侧端点
    re.compile(r"/data/platform"),              # 容器内平台只读挂载点常量（studio 约定）
    re.compile(r"容器内.*(/data/cygnusx|规范路径)"),
    re.compile(r"兜底"),
)


def check() -> int:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(SRC_ROOT).as_posix()
        if rel in _FILE_ALLOWLIST:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            match = _DATA_LITERAL_RE.search(line)
            if match is None:
                continue
            if any(p.search(line) for p in _LINE_ALLOWLIST):
                continue
            violations.append(
                f"❌ {rel}:{lineno}: {match.group(0)} → "
                f"{line.strip()[:100]}"
            )
    if violations:
        print("src/ 中发现 /data/ 字面量绝对路径（禁止写死宿主数据根）：")
        for v in violations:
            print(f"  {v}")
        print(
            "\n修复方式：改由 get_settings().storage_path / "
            "get_storage_config().data_root 派生，或声明为容器内挂载目标。"
        )
        return 1
    print("✅ 存储路径守卫通过：src/ 无 /data/ 字面量新增。")
    return 0


if __name__ == "__main__":
    sys.exit(check())
