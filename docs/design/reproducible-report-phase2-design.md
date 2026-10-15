# 可复现报告 Phase 2 设计

## 范围

Phase 2 将 Phase 1 的 `ReportSnapshot`、执行证据 HTML 和现有科学报告统一为 owner-only 的科研交付包。交付包只整理已经发布并完成字节校验的文件，不启动 RNAFlow，不修改 Task，不重新采集快照，也不宣称已经完成科学复现。

## BioReport 边界

本地 BioReport 仓库当前核验版本为 `2.0.0`，源码提交为 `cb2911a`。其 CLI 合约为 `bioreport run -c <config> -o <output>`，可生成 `report.html` 或 `report.pdf`。CygnusX 通过 `BioReportAdapter` 使用受控子进程调用：仅传入脱敏后的 JSON 配置，强制 single layout，移除 AI module，并设置 `BIOREPORT_AI_ENABLED=false`。不传入数据库凭据、JWT、对象存储凭据或平台内部路径。

HTML 优先复用已经登记且校验过的科学报告；缺失科学 PDF 时，仅在 owner 已登记 BioReport 配置且渲染器可用时尝试受控渲染。渲染失败保留可信 HTML，并在 Manifest 中明确 PDF 缺口，不伪造 PDF。Reproducibility Record PDF 则复用冻结审计 HTML，经受控 Pandoc/Typst 转换，不重新采集事实。BioReport 模板和运行镜像的生产 digest 尚未在当前环境核验，不能把本地仓库版本当成部署验收证据。

## 交付包结构

```text
Scientific_Report.html       # 可选，源报告字节
Scientific_Report.pdf        # 可选，BioReport 产物
Reproducibility_Record.html  # Phase 1 执行证据
ReportSnapshot.json          # 冻结快照
README.md                    # 使用、范围和限制
EvidenceManifest.json        # 机器可读证据清单
checksums.sha256             # 包内字节校验
research-delivery-<id>.zip   # 下载主文件
```

`EvidenceManifest.json` 的 `files` 记录输入报告、快照和 README；Manifest 自身与 `checksums.sha256` 不纳入自身清单，避免自引用哈希循环。验证器拒绝绝对路径、`..`、反斜杠、超出文件数/总大小上限的 ZIP，并逐项校验 Manifest 中可用文件的大小和 SHA-256。

缺失 PDF、HTML 或历史产物时仍可生成 `partial` 包，缺口写入 Manifest 和 README。缺失文件不创建空占位文件。所有报告版本通过既有 `parent_id`/`version` 保留，历史快照不覆盖。

## API 与前端

`POST /api/v1/reports/{report_id}/delivery` 接受科学报告或执行证据报告 ID。若输入是科学报告，服务会查找同一 owner/Task 的最新执行证据报告，并用其冻结快照绑定交付包。重复请求复用同一 delivery 记录；返回的交付报告沿用 ReportsView、owner 鉴权下载、预览隔离和版本历史。

报告预览中增加“生成交付包”操作；交付包本身作为 `report_kind=delivery` 出现在报告中心，主文件为 ZIP。用户仍可单独下载 HTML、PDF、README、Manifest 和快照。

## 安全与验收边界

服务端只读取当前用户报告记录引用的文件，并在打包前复核登记的大小和 SHA-256。输出目录位于用户受控目录；文件名经过 POSIX 路径校验。当前实现不包含跨用户共享、公开链接、自动重运行、签名证明或生产环境的 BioReport image digest 证明。

Phase 2 代码验证不替代真实 RNA Task、PostgreSQL、Celery、对象存储和浏览器闭环验收。未发现 Phase 1.5 live-validation 记录，因此不能将 Phase 1 视为现场验收完成。
