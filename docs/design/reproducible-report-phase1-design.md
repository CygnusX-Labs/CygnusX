# 可复现执行证据报告 Phase 1 设计与实现边界

本文记录本轮最终设计。活动架构权威为 [CygnusX_report_architecture.md](../../ARCHITECTURE_DESIGN/CygnusX_report_architecture.md)；验证证据为 [实施审计](../audits/reproducible-report-phase1-implementation.md)。未引入 Phase 2 / 3、PDF、一键重运行、结果比较或科学渲染框架替换。

## 最终调用链

TaskDetailView → POST tasks/{id}/reproducibility-reports → owner / 终态 RNA Task / 可选 Run 校验 → Job queued 提交 → Celery worker → Phase 0 Builder → 固定 snapshot_id → 离线八模块 HTML → 原子存储并回读 SHA-256 → ReportService 登记 → Job ready → ReportsView 指定报告预览 / 鉴权下载。

ReportModel 保留科学报告，新增 report_kind=reproducibility / snapshot_id / template_version / evidence_partial。沿用 parent_id / version，新增证据产生新版本，不替换 RNAFlow HTML。ReportFile 新增 sha256。快照和 Job 新表由 revision reportauditphase1（父 dynamicrouting03）管理；未运行生产迁移。

## Job 生命周期

queued → collecting → rendering → publishing → ready；相同已发布事实可从 rendering 复用到 ready。任意阶段可 failed。生命周期独立于原始 Task，保存证据完整性、最终 Report / Snapshot ID、固定错误码、安全错误信息、完成时间、尝试次数和恢复路径。

API 用 Task 行锁和活跃 Job 部分唯一索引处理重复/并发请求。可选 UUID Idempotency-Key 对同一 owner / Task / Run / 模板请求固定重用。完成后的新请求重新采集，故磁盘新证据不依赖 Task.updated_at 更新。worker 独占专属连接上的 Task advisory lock，覆盖 commit；最终按 owner+Task+facts digest 和 owner+snapshot+template 两级数据库唯一键去重。

提交 queued 行后尽力投递；Beat 恢复 queued、过期活跃和可重试 failed，弥补提交/队列之间的崩溃窗口。默认报告预算 600 秒、最多 3 次尝试；不会投递分析任务。存储/超时/数据库暂时失败安全重试，权限/身份/协议/摘要损坏不可自动重试。发布重试保存原 snapshot_id，不重新取证；新证据应通过新的生成请求创建新版本。

## 冻结与来源

读取 Task、显式 Run、FileRecord、RunEvent、允许范围的 ARDP 清单与本地文件。数据库采集使用 repeatable-read read-only 事务。捕获窗口和水位体现跨 DB / FS 读取的实际边界；不声称原子执行时取证。六证据状态保持 Phase 0 含义，普通 Task 无 Run 正常生成部分证据报告。

快照 payload 保存 schema/redaction/digest 版本、来源身份、水位、时间与事实；快照 row 既有 ORM 更新拦截又有 PostgreSQL 更新触发器。稳定内容摘要排除生成/采集时钟，保留历史观察与水位、状态及当前字节指纹。optional 文件 display_name 空值不改变旧快照摘要；新快照使用 owner_allowlist.v2 的有界 Unicode 标签投影（支持中文，排除路径/凭据/长令牌），旧 v1 快照仍可读。

历史环境、输入身份、工具调用、QC 决策未知时保留缺口，不引用当前配置、LLM、日志正文或 Prompt 补齐。审计报告不使用当前 Flow catalog 版本冒充历史版本。不安全标签可能被脱敏，缺口说明具体原因。

## HTML 八模块

| 模块 | 呈现规则 |
|---|---|
| M1 概要 | Task/可选 Run、安全名称、状态、分析起止、生成/采集时间、证据完整性 |
| M2 输入环境 | 允许参数、来源与状态；未知输入身份/指纹、软件/镜像/参考版本明确说明 |
| M3 时间线 | Task 生命周期与实际 Run 事件；不按文件时间推造步骤；工具未知则未记录 |
| M4 外部调用 | 仅有可信 Task 关联的摘要；本适配器无记录，显示 not_recorded |
| M5 QC | 测量文件、阈值、质量门、人工豁免分别呈现；文件存在不意味着通过 |
| M6 产物 | 安全名称/引用、类型、大小、校验算法/范围、当前可用性、来源 |
| M7 来源关系 | 真实来源关系与水位，不虚构完整溯源图 |
| M8 限制 | 当前评估、已有条件、缺失依赖、未验证事项；复现验证 not_run |

使用固定模板 audit-v1.0.0。所有值转义；页面含锚点导航、移动布局、状态标签和 CSP，无脚本、外部 CDN 或外部依赖，单 HTML 支持离线阅读。专业科学结果继续由 BioReport 提供。

## 安全和持久化

首版仅 owner 可访问；没有可信项目身份可据以扩展成员权限。API 不收路径。源文件有路径授权、目录 FD/O_NOFOLLOW 取证、普通文件约束、文件前后 fstat 和字节/时间预算。默认哈希总预算 16 GiB；文件/事件/清单数量有限制，超预算明确为缺口。

报告在独立 project run output 下归档，不写历史 tasks 或分析产物。archive_path 在发布前保存；本地 pinned FD 下临时写、fsync、原子 rename，对象存储用完成的 stream 写入；回读长度和 SHA-256 后才在事务中登记目录链、FileRecord、Report/ReportFile 并标 ready。失败文件保持 private、不登记 ready，重试可恢复。没有跨 DB / S3 的分布式事务；终止 Job 留下的孤立 private 归档尚未增加自动 GC。

统一 FileRecord source=report，审计文件 task_id 留空，实际关联在 Report.task_id。这避免把上一份审计报告当成本次科研证据导致自递归摘要变化。现有科学报告 get_by_task_id 仅返回 scientific，避免独立审计版本破坏原报告唯一查询。

预览和下载再次验证 owner/文件关联、路径及 SHA-256；审计本地下载使用已校验字节，关闭校验后重新打开路径的竞争窗口。报告删除后快照旧入口返回 404；文件丢失/改写返回明确错误，不静默覆盖历史交付物。

前端 iframe sandbox 为空，删除可执行同源 HTML 的新窗口入口，下载通过 Bearer API。预览关闭/切换丢弃旧请求，轮询恢复与停止均有状态测试。科学报告脚本交互在平台预览中被禁用，需要下载到本地查看；没有保留 allow-scripts + allow-same-origin 的权限组合。

## 验证与 Phase 2 条件

隔离 ORM + 文件 + ASGI 集成验证可以证明本轮业务路径，不能证明现场 PostgreSQL 锁、Celery broker、S3 或真实 RNA。真实环境缺失时必须明确未验收。附带 opt-in PostgreSQL 测试仅允许显式 report_test 数据库，执行实际迁移并发唯一约束和 trigger 验证；不得用生产 Settings 自动连接。

进入 Phase 2 前需授权可连的 PostgreSQL / broker / 存储、实际应用迁移、一个真实已结束 RNA Task（最好再含显式 Run），完成浏览器 Task → ReportsView → 下载验收。若要提高科学复现等级，还需执行期输入指纹、软件/镜像/参考版本、步骤 IO、工具事件与 QC 决策；固定 BioReport 版本并明确冻结输入适配契约。本轮不提前实现这些后续能力。
