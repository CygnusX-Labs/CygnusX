# 任务：Agent ↔ 沙箱镜像对应关系及镜像内容全面调查

## 一、背景

系统中有 19 个已启用 agent，绑定到 3 类沙箱镜像：

| 镜像 | 绑定的 agent |
|---|---|
| `cygnusx-analysis:core-v0.0.2dev` | agent-atacseq, agent-cloud-ops, agent-code, agent-data, agent-delivery, agent-explorer, agent-mcp-builder, agent-qc, agent-rnaseq, agent-router, agent-skill-builder, agentteams-manager, shania（共 13 个） |
| `cygnusx-analysis:scrna-v0.0.3dev` | agent-general, agent-scrna, agent-scrna-advanced, agent-scrna-integration, agent-scrna-upstream（共 5 个） |
| `cygnusx-analysis:plot-v0.0.2dev` | agent-viz（1 个） |

## 二、总体目标

产出一份《Agent 沙箱镜像调查报告》，回答四个问题：

1. 每个镜像里到底有什么软件？
2. 每个 agent 绑定的镜像是否匹配它的职能？
3. agent 如何知道沙箱里有哪些工具（披露机制）？
4. 每个镜像 / 每个 agent 还缺什么？

## 三、执行步骤

### 第 0 步：定位镜像与运行方式

1. 找到这三类镜像在本机的存储位置（`docker images` / `nerdctl images` / 本地 OCI 目录，或镜像 tar 包），确认镜像的实际 tag 和 digest。
2. 找到启动沙箱的入口：agent 运行时是如何把镜像跑起来的（容器运行时命令、k8s pod 定义、沙箱 SDK 配置等），把启动配置读出来。
3. 找到每个 agent 的定义文件（system prompt / agent 配置 / 绑定关系配置），记录：agent 名字、镜像 tag、system prompt 全文路径。

### 第 1 步：镜像内容盘点（只读，严禁修改镜像）

对**每一类**镜像（不需要对每个 agent 重复，同类镜像只查一次），依次执行以下探测并记录原始输出：

**系统层**

```bash
cat /etc/os-release
uname -a
dpkg -l 2>/dev/null | head -200   # 或 rpm -qa
which python python3 R Rscript gcc g++ make git curl wget pigz samtools ...
echo $PATH
```

**Python 环境**

```bash
python3 --version
pip list --format=freeze
ls /opt/conda 2>/dev/null; conda env list 2>/dev/null
# 对每个 conda 环境分别执行 conda list
find / -name "site-packages" -maxdepth 6 -type d 2>/dev/null
```

**生信 / 分析工具（重点）**

```bash
for t in fastqc fastp cutadapt trimmomatic bwa bwa-mem2 bowtie2 hisat2 star salmon kallisto cellranger cellranger-arc spaceranger velocyto scanpy seurat mono macs2 bedtools bedops deeptools samtools bcftools gatk picard qualimap multiqc nextflow snakemake; do
  echo "== $t =="; which $t && $t --version 2>&1 | head -2
done
```

**参考数据 / 数据库**

```bash
ls /ref /data /genome /references 2>/dev/null
find / -maxdepth 4 \( -name "*.fa" -o -name "*.gtf" -o -name "*.gff3" -o -name "*.bed" \) 2>/dev/null | head -50
df -h  # 看各挂载点
```

**R 环境**

```bash
Rscript -e 'ip <- rownames(installed.packages()); cat(ip, sep="\n")'
```

每个镜像输出一份**软件清单表**，字段：软件名 | 版本 | 安装方式（apt/pip/conda/源码） | 所在环境/路径。

### 第 2 步：Agent-镜像匹配分析

1. 从每个 agent 的 system prompt / 描述中提取其**声明的职能**（例如 agent-atacseq 应能做 ATAC-seq 上游比对、call peak；agent-rnaseq 应能做转录组定量；agent-qc 应能跑 FastQC/MultiQC）。
2. 将职能映射为**所需工具清单**，与第 1 步的实际安装清单比对，输出每个 agent 一张表：

| Agent | 镜像 | 职能 | 已有工具 | 缺失工具 | 结论（✅满足 / ⚠️部分 / ❌不满足） |

特别注意：`core` 镜像被 13 个 agent 共用，其中 agent-atacseq、agent-rnaseq、agent-qc 都有明确生信需求——逐项检查这些工具是否真的在 core 镜像里。

### 第 3 步：工具披露机制调查

1. 通读每个 agent 的 system prompt 全文，检查是否提及任何工具清单、可用软件说明、或"先运行 X 命令探测环境"之类的指令。原文摘录关键句。
2. 检查 agent 运行时是否注入环境变量或挂载清单文件（如 `/etc/motd`、`/opt/tools.json`）。
3. 查看 agent 的历史会话/日志（如可访问），统计 agent 是否出现过：重复安装已存在软件、找不到工具报错、自行 `conda list` 探测等行为。
4. 回答：当前 agent 靠**什么机制**知道沙箱里有什么？该机制的缺陷是什么？

### 第 4 步：改进建议

基于以上发现输出：

1. **镜像增量软件清单**：按 core / scrna / plot 三类，分别列出建议新增安装的软件及版本（含安装方式建议）。
2. **是否需要拆分镜像**：判断 13 个 agent 共用 core 是否合理，哪些 agent（如 agent-atacseq、agent-rnaseq）应拥有独立镜像或扩展镜像。
3. **工具披露方案设计**（重点，至少比较两种方案）：
   - 方案 A：镜像构建时生成 `/opt/agent-tools.json`（含软件名、版本、路径、一句话用途），agent 启动时由运行时注入 system prompt；
   - 方案 B：提供一个 `list_available_tools()` 工具 / MCP server，agent 按需查询；
   - 从可靠性、token 开销、维护成本三个维度对比，给出推荐。

## 四、输出要求

- 产出一份 Markdown 报告，路径 `<工作目录>/sandbox-audit-report.md`，包含：镜像清单、软件清单（三张表）、agent 匹配分析（逐 agent）、披露机制现状、改进建议。
- 报告中每个关键结论后必须附**证据**（实际执行的命令 + 关键输出行），禁止凭印象推断；查不到就明确写"未找到"。
- 镜像和 agent 配置全程**只读**，任何修改类操作（apt install、pip install、写配置）都禁止。
- 最后附一节"执行日志"：列出实际执行过的所有探测命令及其成功/失败状态，便于复跑。

## 五、验收标准

1. 三类镜像的软件清单完整，每条有版本号和安装路径证据；
2. 19 个 agent 每个都有匹配结论（✅ / ⚠️ / ❌ + 缺失工具列表）；
3. 披露机制有明确结论：当前机制是什么、缺陷是什么、推荐改法是什么；
4. 无任何镜像 / 配置被修改。
