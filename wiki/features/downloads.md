# 数据下载

平台「数据下载」入口承载公共数据库下载与云对象存储直拉，复用标准 `Task` 聚合根，并把结果登记为文件资产。

> **当前状态**：下载服务、三种传输来源、Worker 与 FileRecord 登记链已实现；**传输运行验收未完成**（源码 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`），Agent 下载写路径同时受 `WRITE_RUNTIME_ACCEPTED=False` 保护。真实下载能否使用，取决于部署环境的二进制、Worker、网络和验收状态。

## 链路

```text
前端 /downloads
  → POST /api/v1/downloads
  → DownloadService
       → 创建 Task（下载类 flow_id）
       → Celery run_download(task_id)
  → 传输实现
       ├─ EBI/NCBI SRA：EBIDownload
       ├─ 云对象存储：ossutil / tosutil / obsutil
       └─ 受控直接传输：aria2c / ftplib 等
  → 校验与 FileRecord 登记
  → reconcile-only 复核
  → 数据管理 / Dataset
```

下载完成不等于可分析；进入 Dataset 还要经过资产校验、版本冻结与 Handoff，见[Dataset 与 Handoff](../research/dataset)。

## 三种来源

| 来源 | URI/输入 | 依赖 | 备注 |
| --- | --- | --- | --- |
| EBI/NCBI（SRA） | SRR/PRJNA | EBIDownload CLI、YAML、sra-tools | 只接受可解析的 SRR；PRJNA 不能直接传旧入口 |
| 阿里云 OSS | `oss://bucket/path` | ossutil | 需凭证与网络 |
| 火山引擎 TOS | `tos://bucket/path` | tosutil | 需凭证与网络 |
| 华为云 OBS | `obs://bucket/path` | obsutil | 需凭证与网络 |
| 其他受控传输 | URL/云盘 | aria2c/ftplib | 云盘 UI 仍可能是占位，不代表已接通 |

## EBI/NCBI 启用步骤

```bash
cd pipelines/EBIDownload
CC=clang cargo build -p ebidownload-cli --release

mkdir -p /data/cygnusx/bin
cp target/release/EBIDownload /data/cygnusx/bin/
cp EBIDownload.yaml /data/cygnusx/bin/
```

Worker 需要 `sra-tools`：

```bash
mamba install -n base -c bioconda sra-tools
```

环境变量示例（值以部署为准）：

```bash
ENABLE_EBI_DOWNLOAD=true
EBI_DOWNLOAD_BINARY=/data/cygnusx/bin/EBIDownload
EBI_DOWNLOAD_YAML=/data/cygnusx/bin/EBIDownload.yaml
```

## 云存储启用

```bash
ENABLE_CLOUD_STORAGE_DOWNLOAD=true
CLOUD_OSSUTIL_BINARY=/data/cygnusx/bin/ossutil
CLOUD_TOSUTIL_BINARY=/data/cygnusx/bin/tosutil
CLOUD_OBSUTIL_BINARY=/data/cygnusx/bin/obsutil
```

凭证应通过部署密钥或云实例角色管理，不要写入 Wiki、镜像或提交。

## 与 Agent/寻宝鼠的关系

- 平台 AI 通过 `AgentToolGateway` 的 `downloads.*` 能力发现/预案/审批；能力目录会标注“代码存在、配置可用、未认证、执行阻断”。
- 下载预案只接受格式合法的 SRR/PRJNA；GSE/GSM 返回 `NEEDS_METADATA_RESOLUTION`；任意 URL、GEO processed matrix、counts-only DEG 不支持。
- 委托 token 不含 execute/approve；写操作仍要人类确认与源码门禁。
- 下载模块的完整细节（三来源、Worker/CLI 分发、DL-RG 验收）以[下载架构权威文档](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)为准。

## 版本边界

| 对象 | 说明 |
| --- | --- |
| 子模块 EBIDownload | 有自己的版本（曾记录 1.4.0） |
| 旁仓 Polariseq | 独立版本（曾记录 1.4.3） |
| 宿主程序/容器 | 实际运行版本以镜像与部署为准 |

不要把子模块代码版本等同于已部署版本；也不要把文档中的历史版本当作当前版本。

## 排障

| 现象 | 排查 |
| --- | --- |
| 下载任务立即失败 | 检查 `ENABLE_*`、二进制路径、YAML、Worker 依赖 |
| 下载完成但文件不在数据管理 | 检查 FileRecord 登记、reconcile 状态与 owner |
| 云存储 401/403 | 检查凭证、bucket 权限与网络 |
| Agent 下载被拒 | 检查源码写门禁、确认状态和能力目录，不要改环境变量绕过 |
| 任务一直 QUEUED | 检查 Celery Worker、队列路由和投递对账 |

## 关联文档

- 权威基线：[`CygnusX_download_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)
- [数据发现与获取](../research/data-discovery) · [Dataset 与 Handoff](../research/dataset) · [科研能力与证据边界](../research/evidence-boundaries)
- [问题排查](../operations/troubleshooting)
