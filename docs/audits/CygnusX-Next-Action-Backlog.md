# CygnusX 下一步行动清单

按依赖和风险排序。仅列可执行的最小任务；外部材料到齐前不启动运行 Gate。

| # | 优先级 | 类别 | 最小行动与验收 | 阻断/输入 | Codex 可立即做？ | Owner |
|---|---|---|---|---|---|---|
| 1 | P0 | 源码冻结 | 明确当前 HEAD 与全部 dirty/submodule 变化归属；选定干净冻结 commit；clean build 并保存 source、lock、dist、镜像完整 digest 对照；验收是所有摘要可从冻结源码重建 | 需负责人确认哪些现存脏改动进入 RC；不可在本次审计擅自整理 | NO，先需确定冻结范围 | Release Owner（未分配） |
| 2 | P0 | 运行准入 | 在批准 disposable 环境关闭/核对持久 READS/WRITES/PDF，采集运行进程有效状态、容器/卷状态和脱敏配置；验收 Gate 关闭且保留卷可复核 | 需隔离环境和执行授权 | NO | Acceptance Operator（未分配） |
| 3 | P0 | RA02 完整性 | 在真实隔离 PG 重跑 RA02 11 项并恢复 `RA02_12 legal update` 正向 SQLSTATE `00000`；验证断言总数和报告摘要一致 | 需要隔离 PG 运行权限 | AFTER_AUTHORIZATION | DB/Acceptance Owner（未分配） |
| 4 | P0 | 浏览器 Core | 形成 34 项具名 assertion 对账；分别在 1920/768/390 跑 fresh UI export 与 existing-ready 幂等复用，断言 ready、按钮/下载可用、ZIP SHA、无重复发布 | 需当前冻结镜像、测试账号和 disposable 环境 | AFTER_AUTHORIZATION | E2E Owner（未分配） |
| 5 | P0 | FI01–FI06 | 评审最小注入设计，然后在 disposable PG/Worker 中覆盖 validating/rendering/publishing、发布后提交前、重复投递、撤权；每项证明状态恢复、无幽灵登记和生产默认禁用 | 先定义 FI 与授权注入环境 | NO，需评审与授权 | Acceptance/Security Owner（未分配） |
| 6 | P1 | 安全与证据 | 独立审查默认/定制 seccomp 逐项差分、容器作用域、capabilities；复核 artifact index 每条 SHA/大小/Run ID/脱敏/断言语义 | 需要安全审查者与完整索引材料 | YES（只读文档审查可继续） | Security Reviewer（未分配） |
| 7 | P1 | Full 旧库 | 导入获批脱敏旧库快照至独立卷，记录 schema/Alembic/data/artifact 前后状态并升级；验收保留历史业务事实及交付文件 | 需要旧库和制品基线批准 | NO | DB Owner（未分配） |
| 8 | P1 | Full 外部存储 | 提供冻结历史 M0/ZIP corpus、独立 S3 Bucket/前缀和异常 fixture；跑跨版本字节比较、上传回读/撤权及漂移/丢失/symlink/配额隔离测试 | 需要 corpus、S3 授权与安全 fixture | NO | Data/S3 Owner（未分配） |
| 9 | P1 | Gate 定义 | 找回并登记 RA04–06 原始契约，逐条映射当前测试、Run ID 和缺项；不可仅按旧实现报告推断语义 | 需要原始定义来源 | NO | Acceptance Owner（未分配） |
| 10 | P2 | 科研复现里程碑 | 批准至少一个小型公开/合规真实 RNA-seq 案例，完成数据 provenance→校验→冻结 FlowFrame/RNAFlow→真实执行→科学 BioReport→Evidence/Manifest→独立重放 | 依赖样本选择、资源与运行环境批准；项目摘要 PDF 不可替代 | NO | Scientific Lead（未分配） |

## 最小推进顺序

先确定当前工作树冻结范围，再准备 disposable 验收环境；随后恢复 RA02 正向断言、补浏览器矩阵和 FI 证据，完成证据/安全复核。只有 Core 通过后才并行准备旧库、corpus、S3 与 RA04–06 原定义。真实科研复现作为独立科学里程碑执行，不能合并进 RC04-Core 完成率。
