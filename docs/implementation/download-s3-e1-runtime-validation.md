# S3-E1 Runtime Readiness & Minimal Execution Validation

核实日期：2026-10-16。完整阅读[最新S3-E1报告](download-s3-e1-trusted-execution-boundary.md)和[活动下载架构](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)，以当前工作树与本轮只读观察为依据。

**结论：BLOCKED。** 当前未提供明确授权的非生产运行入口，也未证明可用的可信执行设施。按本轮任务一要求，完成只读检查、列出阻断与最小资源后停止。不实现新驱动、不重复接口、不新增Mock测试、不尝试真实下载。

## 状态定义与本轮结果

| 状态 | 本轮结论与证据范围 |
|---|---|
| DESIGN_COMPLETE | 既有S3-E1接口及目标边界设计已交付；不表示选定设施已可部署或认证 |
| CODE_COMPLETE | **未达到**可信运行实现完成；当前只有Protocol/模型/必要条件检查和验收骨架，缺具体adapter、监督器接线及真实驱动 |
| PASS_ISOLATED | 上轮记录146 passed、9 skipped、1 warning，只证明其列出的本地契约/门禁/登记边界；本轮没有重跑pytest，不将旧数字作为本轮测试结果 |
| PASS_RUNTIME | **未达到 / NOT_TESTED**；没有真实Task、CLI传输、网络硬限、quota、取消或Worker异常清理证据 |
| BLOCKED | 本轮运行准备检查结果；G3仍 **PARTIAL_CODE / RUNTIME_BLOCKED**，下一阶段真实执行不准入 |

本轮实际完成代码：**无生产代码或测试程序变更**。仅新增本文及`evidence/download-s3-e1-runtime-validation/`观察记录。没有改既有接口、fixture、开关、锁文件、部署、数据库或用户数据；未提交、推送。工作区基线及HEAD已保存。

## 只读环境检查

原始证据：`host-readiness.json`时间为`2026-10-16T14:22:37.610494+00:00`；`dependencies.json`来自复用现有`check_download_execution_boundary.py`。scope均为 **HOST_READ_ONLY_NOT_WORKER**，不是生产/隔离Worker观察。

| 检查项 | 实际观察 | 判断与限制 |
|---|---|---|
| Linux/cgroup v2 | x86_64，内核`6.8.0-147-generic`；cgroup2可见，controllers含cpu/io/memory/pids等 | 基础支持可见；不是任务资源硬限已生效 |
| cgroup操作范围 | `/sys/fs/cgroup`挂载`ro`，写权限提示false；当前进程在用户tmux scope | 当前挂载不能直接建任务scope；没有提供其他授权委托接口 |
| 当前权限 | UID/GID1000，CapEff全0，NoNewPrivs=1 | 无当前命名空间有效管理capability；不尝试提权或安装组件 |
| namespace/容器能力 | user/net/mnt/pid句柄可见；unshare/nsenter/docker命令存在；userns开关为1、max_net_namespaces为正 | 只证明可见性和配置，不证明创建权限或可用安全隔离。未执行unshare、setns、容器API或启动容器 |
| 文件系统/project quota | 工作区、`/tmp`为ext4可写挂载；`/data/omichub`匹配根ext4只读挂载；xfs_quota程序存在 | 未取得FS project功能、quota启用/限额/委托证据；不能据程序存在推断XFS或硬quota。未查询受保护宿主设备、重挂载或设置quota |
| 独立写目录 | 工作区和`/tmp`有写权限提示；没有提供Task独占容量卷 | 可写目录不等于任务隔离、容量硬限或Worker共享存储；未创建下载目录 |
| CLI | 配置`/usr/bin/aria2c`不存在，PATH也未找到；EBIDownload文件存在；tosutil不可执行，ossutil/obsutil不存在 | 属宿主视图。未执行CLI version/help，不冒充Worker版本；首选HTTP下载器尚不可用 |
| Worker镜像 | Compose仍声明共享Worker及Docker socket、`.env`、共享数据盘 | 只是源码部署声明。未获隔离Worker端点/身份，实际容器digest、UID、工具版本、挂载UNKNOWN |
| 网络出口 | 未提供可信出口接口、策略版本、同步RX计量与硬限证明 | UNKNOWN/BLOCKED；未访问HTTP、DNS、私网或探测生产网络 |
| 监督机制 | 当前在用户scope，systemctl命令存在；适配器仅Protocol，未提供独立租约监督器 | 没有Worker失联后断出口/清空后代的证明；普通service manager存在不等于任务监督实现 |

Docker socket路径可见，但本轮未连接，也不沿用旧PermissionError作为本轮实时权限结论。未读取`.env`或输出环境变量/凭据值。当前信息不足以断言宿主完全不支持隔离，也不足以授权使用任何宿主设施。

## 执行与测试记录

本轮实际执行：

```bash
.venv/bin/python scripts/check_download_execution_boundary.py \
 --output evidence/download-s3-e1-runtime-validation/dependencies.json
```

另用一次性Python只读采集`platform.release()`、`/proc/self/status`（现有脚本）、`/proc/self/cgroup`、cgroup controllers、namespace句柄、选定挂载的mountinfo、userns配置、工具路径和文件存在/执行权限提示；写入`host-readiness.json`。没有保存新的等价检查程序。源码复核确认`TrustedExecutionAdapter`无具体实现，BinaryExecutor仍直接启动子进程，真实HTTP测试fixture仍明确skip。

这些是环境观察，**不是隔离测试通过**。本轮没有pytest、CLI、网络下载、quota满、取消、SIGKILL或DB对账测试。按环境不满足即停止的要求，没有为制造测试数量重复运行旧契约集合。

实际运行证据字段：Task ID、Execution Scope ID、Worker/CLI实际版本、真实网络字节、任务quota、停止证明、FileRecord ID和文件SHA-256均为 **N/A（未执行）**，不是0或成功。当前编码进程cgroup路径不能充作下载Scope ID；没有创建虚构Task、FileRecord或Dataset记录。

## 阻断与最小环境资源

1. **明确授权**：指定非生产机器/隔离Worker及访问方式、测试owner/project、允许动作（含测试Worker终止）、自有HTTP源与受控未授权目标、累计网络/磁盘/inode/时间上限、清理范围。当前任务是条件授权，尚未给出具体获授权环境和目标，不能选择生产资源代替。
2. **可操作的隔离设施**：运维预置受信接口建立每Task cgroup及network/mount范围；普通下载进程非root、无NET_ADMIN/NET_RAW、无Docker socket、DB/broker及其他用户文件访问。不能用当前共享Worker直接替代受限scope。
3. **网络硬边界**：唯一受控出口，IPv4/IPv6与DNS/实际连接绑定、逐跳HTTP检查、直连及替代代理拒绝；所有连接/重试同步共享实际RX硬额度并输出可信计数、单位、观测点和策略版本。
4. **文件系统硬边界**：运维提供Task独占卷或已验证project quota，含块/inode限额和查询权限，覆盖输出/HOME/TMP/cache等所有写路径；父存储有余量。当前ext4可写目录不满足此证明。
5. **生命周期与原链路环境**：独立于Worker的租约/deadline监督与停止证明；可信身份/admission/budget引用解析；隔离DB/broker及现有Task/FileRegistry/Dataset服务用于真实登记/对账，不另建业务系统。
6. **版本与驱动**：锁定Worker镜像digest和aria2c路径/版本/hash，运维提供只读观察；在上述条件齐备后实现并审查现有`TrustedHttpDriver`真实驱动。只复用`tests/integration/test_download_trusted_http_boundary.py`，不得用Mock或手填FileRecord代替。

## 下一阶段准入与保护

上述资源、授权和实现均有可核验证据后，才可接入真实驱动，先证明网络与所有写路径不能逃逸，再在明确小额度内执行九场景。逐例保存Task/scope、Worker/CLI版本、初末真实RX/硬限、quota、空进程树与出口撤销、原FileRecord/实算SHA及失败原因；正常文件经原链登记，部分文件沿原失败/取消/对账语义，不能产生科研虚假成功。

当前`DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`和Gateway `WRITE_RUNTIME_ACCEPTED=False`均保留；TransportAdmission无可信协议证书消费。测试驱动不得自行翻门禁，须在后续经审查的隔离接线中保留服务端身份、原审批与认证检查。HTTP即使验收通过也不自动放生产，更不开放FTP、HTTPS、EBIDownload或云存储；模型标签不能证明认证。

本轮没有运行接线，原`Task → FileRegistry → FileRecord → DatasetAsset → DatasetVersion`不变，无数据库/业务回滚需求。若撤回本轮交付，仅移除本文及本轮观察记录，保留此前文件、脏改动和用户数据。按要求到此停止；这是受限环境检查交付完成，**不是最小真实执行完成**。
