# Agent 沙箱镜像改造与工具披露机制优化方案

> 依据：`sandbox-audit-report.md`（2026-10-03）。本方案只改 `deploy/`、`data/ai/`、`src/cygnusx/infrastructure/` 与 3 个 agent YAML，不改其余 16 个 agent。

---

## 第一部分：为 agent-atacseq / agent-rnaseq / agent-qc 建立专用镜像

### 1.1 设计原则

- 三个新 profile 全部 `extends: analysis-core`，与 plot/scrna 的继承方式一致，不触碰现有镜像。
- core 保持"通用统计/代码运行时"，不为 NGS 工具增肥。
- 四份文件必须同步改：**Dockerfile、runtime_images.yaml、image-mapping.yaml、agent YAML 的 `studio.runtime_profile`**，并在 Dockerfile 构建期做存在性校验（与现有 plot/scrna Dockerfile 的校验风格对齐）。
- 版本建议先宽松锁定（`>=` 或固定 bioconda 最新稳定版），等第 10 节复测拿到实测版本后再收紧。

### 1.2 新增 `deploy/runtime-images/rnaseq.Dockerfile`

```dockerfile
# cygnusx-analysis:rnaseq —— 派生自 analysis-core
FROM cygnusx-analysis:core-v0.0.2dev

# RNA-seq 上游比对 + 定量 + QC
RUN micromamba install -y -n base -c bioconda -c conda-forge \
        star \
        salmon \
        rsem \
        samtools \
        fastp \
        multiqc \
        subread \
    && micromamba clean -a -y

# 构建期校验：CLI 可执行且能输出版本号
RUN micromamba run -n base sh -c ' \
    for t in STAR salmon rsem-calculate-expression samtools fastp multiqc featureCounts; do \
        which $t >/dev/null || { echo "MISSING: $t"; exit 1; }; \
    done; \
    echo "rnaseq runtime OK"'
```

### 1.3 新增 `deploy/runtime-images/atacseq.Dockerfile`

```dockerfile
# cygnusx-analysis:atacseq —— 派生自 analysis-core
FROM cygnusx-analysis:core-v0.0.2dev

# ATAC-seq 比对 + peak calling + 信号/QC
RUN micromamba install -y -n base -c bioconda -c conda-forge \
        bowtie2 \
        chromap \
        macs2 \
        samtools \
        bedtools \
        deeptools \
        fastp \
        multiqc \
    && micromamba clean -a -y

RUN micromamba run -n base sh -c ' \
    for t in bowtie2 chromap macs2 samtools bedtools bamCoverage fastp multiqc; do \
        which $t >/dev/null || { echo "MISSING: $t"; exit 1; }; \
    done; \
    echo "atacseq runtime OK"'
```

> 注意：若决定二选一改用 Chromap 作默认比对器，可从清单中去掉 bowtie2 以减小体积；先保留两者，由 prompt 声明默认推荐。

### 1.4 新增 `deploy/runtime-images/qc.Dockerfile`

```dockerfile
# cygnusx-analysis:qc —— 派生自 analysis-core
FROM cygnusx-analysis:core-v0.0.2dev

# 通用 NGS QC：FastQC/fastp/MultiQC + BAM/VCF 检查；Kraken2/Bracken 按需选装
RUN micromamba install -y -n base -c bioconda -c conda-forge \
        fastqc \
        fastp \
        multiqc \
        samtools \
        bcftools \
        deeptools \
        qualimap \
        fastq-screen \
    && micromamba clean -a -y

# 可选宏基因组污染评估层（体积较大，按需启用）
# RUN micromamba install -y -n base -c bioconda kraken2 bracken && micromamba clean -a -y

RUN micromamba run -n base sh -c ' \
    for t in fastqc fastp multiqc samtools bcftools bamCoverage qualimap; do \
        which $t >/dev/null || { echo "MISSING: $t"; exit 1; }; \
    done; \
    echo "qc runtime OK"'
```

### 1.5 `data/ai/runtime_images.yaml` 新增三个 profile

格式对齐现有 profile（capabilities / languages / software / resources 字段名以文件现状为准）：

```yaml
profiles:
  # ... 现有 analysis-core / analysis-plot / analysis-scrna 保持不变 ...

  analysis-rnaseq:
    extends: analysis-core
    image: cygnusx-analysis:rnaseq-v0.0.1dev
    capabilities: [ngs, rnaseq, qc]
    languages: [python, r, bash]
    software:
      - { name: star,      version: ">=2.7",   path: /opt/conda/bin/STAR }
      - { name: salmon,    version: ">=1.10",  path: /opt/conda/bin/salmon }
      - { name: rsem,      version: ">=1.3",   path: /opt/conda/bin/rsem-calculate-expression }
      - { name: samtools,  version: ">=1.20",  path: /opt/conda/bin/samtools }
      - { name: fastp,     version: ">=0.23",  path: /opt/conda/bin/fastp }
      - { name: multiqc,   version: ">=1.24",  path: /opt/conda/bin/multiqc }
      - { name: subread,   version: ">=2.0",   path: /opt/conda/bin/featureCounts }
    resources: { cpu: 8, memory_gb: 32, disk_gb: 50 }

  analysis-atacseq:
    extends: analysis-core
    image: cygnusx-analysis:atacseq-v0.0.1dev
    capabilities: [ngs, atacseq, qc]
    languages: [python, r, bash]
    software:
      - { name: bowtie2,   version: ">=2.5",   path: /opt/conda/bin/bowtie2 }
      - { name: chromap,   version: ">=0.2",   path: /opt/conda/bin/chromap }
      - { name: macs2,     version: ">=2.2",   path: /opt/conda/bin/macs2 }
      - { name: samtools,  version: ">=1.20",  path: /opt/conda/bin/samtools }
      - { name: bedtools,  version: ">=2.31",  path: /opt/conda/bin/bedtools }
      - { name: deeptools, version: ">=3.5",   path: /opt/conda/bin/bamCoverage }
      - { name: fastp,     version: ">=0.23",  path: /opt/conda/bin/fastp }
      - { name: multiqc,   version: ">=1.24",  path: /opt/conda/bin/multiqc }
    resources: { cpu: 8, memory_gb: 32, disk_gb: 50 }

  analysis-qc:
    extends: analysis-core
    image: cygnusx-analysis:qc-v0.0.1dev
    capabilities: [ngs, qc]
    languages: [python, r, bash]
    software:
      - { name: fastqc,    version: ">=0.12",  path: /opt/conda/bin/fastqc }
      - { name: fastp,     version: ">=0.23",  path: /opt/conda/bin/fastp }
      - { name: multiqc,   version: ">=1.24",  path: /opt/conda/bin/multiqc }
      - { name: samtools,  version: ">=1.20",  path: /opt/conda/bin/samtools }
      - { name: bcftools,  version: ">=1.20",  path: /opt/conda/bin/bcftools }
      - { name: deeptools, version: ">=3.5",   path: /opt/conda/bin/bamCoverage }
      - { name: qualimap,  version: ">=2.3",   path: /opt/conda/bin/qualimap }
    resources: { cpu: 4, memory_gb: 16, disk_gb: 30 }
```

### 1.6 `deploy/image-mapping.yaml` 新增映射

对齐现有条目格式（第 8–18 行的风格）：

```yaml
runtime_profiles:
  # ... 现有三条保持不变 ...
  analysis-rnaseq:
    image: cygnusx-analysis:rnaseq-v0.0.1dev
    dockerfile: deploy/runtime-images/rnaseq.Dockerfile
    extends: analysis-core
  analysis-atacseq:
    image: cygnusx-analysis:atacseq-v0.0.1dev
    dockerfile: deploy/runtime-images/atacseq.Dockerfile
    extends: analysis-core
  analysis-qc:
    image: cygnusx-analysis:qc-v0.0.1dev
    dockerfile: deploy/runtime-images/qc.Dockerfile
    extends: analysis-core
```

### 1.7 改三个 agent YAML 的 `studio.runtime_profile`

```yaml
# data/agents/agent-atacseq.yaml（或实际路径）
studio:
  runtime_profile: analysis-atacseq   # 原为 analysis-core
```

```yaml
# agent-rnaseq
studio:
  runtime_profile: analysis-rnaseq
```

```yaml
# agent-qc
studio:
  runtime_profile: analysis-qc
```

同时把三个 agent prompt 里"环境缺包请降级/转交"的兜底句改成"若确需清单外工具，走缺包上报流程"——现在镜像已经兑现了声明，不需要再自我降级。`sandbox_protocol.md` 的缺包上报流程保持不变。

### 1.8 验证清单

1. 构建三个镜像，确认 Dockerfile 末尾的 `xxx runtime OK` 校验通过；
2. 跑现有 image-mapping 校验脚本（调查报告中提到 image mapping validation 已通过 14 张图，应有对应测试）+ 新增三个 profile 的绑定断言；
3. 各起一个容器手动跑一条最小流程（STAR --genomeLoad 不必，至少 `fastp` 处理一个小 fastq、`multiqc` 汇总）；
4. 确认其余 16 个 agent 的 `runtime_profile` 未被波及。

---

## 第二部分：工具披露机制优化（A + B 终态）

### 2.1 目标

让 agent 看到的工具清单 = **构建期实测 + 运行期可复核**，消灭"声明漂移"。

### 2.2 方案 A：构建期生成 `/opt/agent-tools.json`

**新增 `deploy/runtime-images/scripts/render_tools_manifest.py`**（在构建容器内运行，只读探测）：

```python
#!/usr/bin/env python3
"""构建期工具清单生成器。
对每个声明工具执行 which + --version（或 python import / R library 探测），
输出 /opt/agent-tools.json；任一 probe_status=missing 时 exit 1 让构建失败。"""
import json, shutil, subprocess, sys

def probe_cli(path_hint: str | None, name: str):
    exe = path_hint if path_hint and shutil.which(path_hint) else shutil.which(name)
    if not exe:
        return {"name": name, "probe_status": "missing"}
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        first = (v.stdout or v.stderr).strip().splitlines()[0][:200]
    except Exception as e:
        first = f"version probe failed: {e}"
    return {"name": name, "version": first, "path": exe,
            "source": "micromamba", "probe_status": "ok"}

def main(catalog_path: str, out_path: str):
    catalog = json.load(open(catalog_path))          # 从 runtime_images.yaml 转出的本 profile 条目
    entries = [probe_cli(s.get("path"), s["name"]) for s in catalog["software"]]
    manifest = {"profile": catalog["profile"], "image": catalog["image"],
                "generated_by": "render_tools_manifest.py", "tools": entries}
    json.dump(manifest, open(out_path, "w"), indent=2, ensure_ascii=False)
    missing = [t["name"] for t in entries if t["probe_status"] != "ok"]
    if missing:
        print(f"BUILD FAILED — missing tools: {missing}", file=sys.stderr)
        sys.exit(1)
    print(f"{len(entries)} tools verified -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

**每个 Dockerfile 末尾追加**（含现有的 core/plot/scrna 也补上，保证六类镜像契约一致）：

```dockerfile
# 工具清单生成：声明 -> 实测，缺工具则构建失败
COPY deploy/runtime-images/scripts/render_tools_manifest.py /opt/cygnusx/
RUN micromamba run -n base python /opt/cygnusx/render_tools_manifest.py \
        /opt/cygnusx/profile-tools-declared.json /opt/agent-tools.json \
    && cat /opt/agent-tools.json
```

（`profile-tools-declared.json` 由构建脚本从 `runtime_images.yaml` 提取当前 profile 生成。）

**同步把 manifest 摘要写入 OCI label**，供 Studio 侧不启容器即可读到：

```dockerfile
LABEL org.cygnusx.tools-manifest.digest="see-build-script"
# 构建脚本在 docker build 后执行：
#   docker image inspect <img> --format '{{.Id}}' 与 sha256(/opt/agent-tools.json) 记入 image-mapping.yaml 的 digest 字段
```

### 2.3 方案 A 的注入链路（修改 `src/cygnusx/infrastructure/config/runtime_image_loader.py`）

优先级从高到低，取第一个可用来源：

1. **镜像 label / image-mapping digest**：`studio/manager.py::ensure_running()` 在容器创建后，从 sandbox-agent socket 拉取一次 `/opt/agent-tools.json`（见 2.4 的 runtime endpoint），缓存于会话；
2. **回退**：现有 `render_runtime_manifest()` 的静态声明（保持现状不变，作为降级路径）。

system prompt 中渲染格式建议收敛为：

```text
[runtime-tools]
profile: analysis-atacseq (cygnusx-analysis:atacseq-v0.0.1dev, digest sha256:xxxx)
verified at build: 8 tools
  - macs2  2.2.9.1  /opt/conda/bin/macs2  —— ATAC peak calling
  - ...
probe on demand: list_available_tools(pattern="*")
```

比现状多三样信息：**digest、构建期校验通过数、按需探测入口**。

### 2.4 方案 B：只读运行时探测工具 `list_available_tools`

**在 `sandbox_agent.py` 增加一个 socket endpoint**（容器内，只读）：

```
request:  {"op": "list_tools", "pattern": "macs*", "verify": true}
response: {"tools": [{name, version, path, probe_status}], "source": "runtime"}
```

- `verify: false` —— 直接读 `/opt/agent-tools.json`（零开销）；
- `verify: true`  —— 对匹配工具现跑 `which` + `--version` 复核，用于版本漂移场景；
- 任何写操作、安装操作一律拒绝，复用现有 capability 审计，记 `sandbox.tool_probe` 事件到 `infrastructure/studio/audit.py`。

**给 agent 的暴露方式**：在 agent 的工具白名单中注册 `list_available_tools(pattern, verify)`，实现为 Studio 侧一次 sandbox-agent socket 调用。为控制 token：默认只注入工具名+一句话用途，版本/路径按需返回。

### 2.5 漂移防护（让 prompt 不再撒谎）

- `runtime_images.yaml` 每个 profile 增加 `tools_manifest_digest` 字段；
- `manager.py::ensure_running()` 比对"本地镜像的 manifest 摘要"与注册表 digest：**不一致 → 触发 `sandbox.rebuild` 审计事件并在 prompt 里标注 `manifest_stale: true`**，而不是静默使用旧声明；
- CI 增加一步：构建后若 `render_tools_manifest.py` 输出与 `runtime_images.yaml` 声明的版本约束冲突（如声明 `>=2.5` 实测 `2.4.5`），构建失败。

### 2.6 落地顺序（建议）

| 阶段 | 内容 | 风险 |
|---|---|---|
| P1 | 三个新 Dockerfile + yaml/agent 绑定（第一部分） | 低，纯增量 |
| P2 | `render_tools_manifest.py` 接入六个镜像构建 + digest 记录 | 低，只影响构建 |
| P3 | Studio 注入链路改读 manifest + `manifest_stale` 标记 | 中，改 prompt 渲染，需回归 |
| P4 | `list_available_tools` endpoint + agent 工具注册 + 审计事件 | 中，新工具面，需权限评审 |

P1 做完那三个 ❌ 就变成 ✅；P2–P4 解决的是全部 19 个 agent 的披露可信度问题。

### 2.7 不做的事

- 不给沙箱开网络装包（`CygnusX_network_architecture.md` 的默认无网络约束不变）；
- 不在容器启动时动态 `pip list` 全量扫描注入 prompt（token 浪费，且与构建期校验重复）；
- 不引入第三个"平台候选包"清单——`bio_packages.md` 继续只作候选索引，prompt 渲染时明确标注其性质，避免与已安装清单混淆。
