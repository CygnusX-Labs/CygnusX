# S3 Runtime Enforcement Closure：运行约束选型与交接

日期：2026-10-16。依据用户本轮四阶段任务、[最新 Closure 报告](download-s3-closure-implementation.md)与[活动下载架构](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md)。本文为源码/部署声明调查与待实施设计，**不是实际 Worker 观察、运行认证或部署变更**。

本轮环境不可访问授权隔离 Worker，按任务允许的分支完成技术设计、兼容性检查与无副作用测试。未改生产代码、测试替身、开关、镜像、网络或数据库；未启动下载器。G3 仍为 **PARTIAL_CODE / RUNTIME_BLOCKED**。

## 1. 当前运行时边界

### 1.1 已核实的调用链

| 层 | 代码或声明事实 | 安全含义 |
|---|---|---|
| Worker 部署 | `deploy/docker/docker-compose.worker.yml:worker` 消费 analysis 等队列；连接 cygnusx_net，env_file 引入 .env；挂载共享数据盘及 Docker socket，src/pipelines只读，tool_configs未声明只读 | 这是部署声明，真实容器未知。不能将持有数据库、broker、Docker访问能力的整个Worker当成受限下载沙箱 |
| 镜像 | `Dockerfile.worker` 是 Python/Celery/Snakemake/Micromamba/Docker CLI 镜像；下载工具路径由配置指向外置盘 | Dockerfile不证明外置工具在运行容器内存在或来源一致 |
| BinaryExecutor | `create_subprocess_exec(*cmd, cwd=...)`，没有指定受限env、任务network/mount namespace或cgroup；等待父进程退出，排空日志 | 不使用shell不等于网络隔离；默认继承环境/网络/权限；日志过滤不限制socket或写盘 |
| FTP目录枚举 | Worker `_expand_ftp_directories` 在BinaryExecutor之外直接构造ftplib.FTP，递归限深/条目/超时 | 仅包住CLI会遗漏这条控制/数据连接路径，必须纳入同一隔离单元或保持递归BLOCKED |
| SRA | Worker调用EBIDownload，传YAML、accession/method、输出目录、progress端口和key开关 | YAML/依赖路径和进度监听也是受控资源，不能只保护下载URL |
| 生命周期 | `TaskService.cancel_task` 更新Task CANCELLED；BinaryExecutor未提供下载进程树停止确认 | DB取消不证明子进程退出；Worker退出不保证wget/fasterq等后代已停止 |

S1真实Task/source/SHA、原FileRegistry、Dataset reconcile、协议重验、日志投影均保留，不重做S0–S2。

### 1.2 实际环境可见性

本轮只读宿主观察见 `evidence/download-s3-runtime-enforcement/host-observation.json`，明确scope为HOST_READ_ONLY_NOT_WORKER：

- Docker socket连接返回PermissionError(errno 1)，未发送Docker API请求；无法观察容器digest、UID、mount、进程或实际网络策略。
- 配置默认路径的aria2c、ossutil、obsutil不存在；tosutil文件存在但当前用户不可执行；wget与EBIDownload存在且记录了SHA。**未执行任何程序获取version/help**。
- 宿主存在文件不证明容器内同版本、可执行性或配置；三云参数兼容均未知。不能声称“已调查生产运行实况”。

## 2. 下载器调用与兼容性矩阵

| 后端 | 当前可核实调用方式 | 网络/代理及绕过边界 | 临时/转换/重试 | 本轮兼容结论 |
|---|---|---|---|---|
| aria2 HTTP/HTTPS | `_build_direct_link_args`设置continue、重试、连接/读超时、并发、split等 | 官方有proxy选项，但当前argv未强制可信出口；配置文件/环境可能影响连接。CONNECT本身不提供明文逐跳证明 | 多连接、续传、aria2 sidecar；速度限制不是累计字节硬限 | 源码候选；Worker版本未知；BLOCKED |
| aria2 FTP | 同一argv，有ftp-reuse-connection | 控制与数据通道均须受约束，不能由HTTP成功推导FTP合格 | 目录预枚举还在Python Worker；列表和所有数据流都计费 | 未认证被动数据通道；BLOCKED |
| EBIDownload aws | 子仓CLI main.rs调用core/aws_s3.rs，reqwest元数据/Range分块下载，再启动fasterq-dump并压缩 | Rust直接socket不由Python URL预校验绑定；各reqwest client需核对DNS/代理/redirect行为 | chunk/重试/断点、SRA和FASTQ同时存在、转换临时文件；进度的估算量不等于账本 | 源码候选；运行二进制未对齐；BLOCKED |
| EBIDownload ftp / wget | core/ftp.rs使用 `Command::new("wget")` 与 `-c URL`，由PATH解析wget；独立MD5检查 | wget是后代进程；即使父CLI用代理，子进程也可能独立连接；须纳入同一namespace/cgroup | 续传/重试/元数据文件；总流量不可按最终文件长度计算 | wget宿主存在不证明Worker；BLOCKED |
| ossutil | `_build_cloud_storage_args`：cp/update/force/jobs，可递归 | endpoint、代理、认证配置受实际版本影响，未取得Worker help，不能假设支持指定proxy/预算选项 | multipart/重试/缓存具体位置未认证 | 参数为平台声明，真实兼容UNKNOWN；BLOCKED |
| tosutil | cp/-u/-j/--checkpoint，可递归 | 同上，不能以环境变量保证无直连 | checkpoint在work_dir，其他HOME/TMP/cache仍需实际测试 | 宿主文件不可执行；WorkerUNKNOWN；BLOCKED |
| obsutil | cp/-f/-u/-j/-parallel/-partSize，可递归 | 同上；不得把签名URL或密钥写到日志/argv | multipart及临时配置路径需独立认证 | WorkerUNKNOWN；BLOCKED |
| FTPS/Aspera/泛S3/COS/云盘 | 无获准平台执行适配 | 不fallback成FTP或其他来源 | 不适用 | UNSUPPORTED/UI_ONLY |

源码重点：`pipelines/EBIDownload/crates/ebidownload-{cli,core}/src/`。CLI `--max-size`明确只适用于Prefetch，平台仅aws/ftp，不能当这两条路径的硬限。`http_server.rs`进度服务绑定0.0.0.0，隔离后必须收窄可达面和认证，不可把进度端口暴露为外网/宿主任意转发。

aria2官方文档说明代理选项和下载速度限制；不能据此推导累计预算或实际Worker支持：[aria2手册](https://aria2.github.io/manual/en/html/aria2c.html)。

## 3. 选型：任务隔离为共同底座，应用出口逐协议认证

| 候选 | 优点 | 无法独立满足的要求 | 决策 |
|---|---|---|---|
| 仅设置HTTP_PROXY/CLI proxy/env | 改动小 | 子进程/config/no_proxy/原始socket可直连；FTP/PASV与转换不覆盖；无磁盘硬限 | 拒绝作为安全边界 |
| 仅解析DNS/IP白名单/目录轮询 | 可前置提示和诊断 | DNS变化、重定向、轮询超调；不能证明实际连接/累计量 | 只保留辅助用途 |
| 把整个共享Worker限流/配额 | 运维容易定位 | 多Task和PG/Redis共用网络、盘和进程；不能归属单Task，也不能安全取消整Worker | 不采用 |
| 每Task隔离网络+文件系统配额+cgroup监督 | 可覆盖所有后代与直接socket，隔离PG/Redis/Docker权限 | 仍需可信出口策略、预算执行与实际平台支持；不是已有实现 | 推荐共同底座，待授权环境验证 |
| 底座内使用受控协议出口 | 可负责真实解析/逐跳与明文流量预算 | HTTPS CONNECT不解密看不到Location；FTP需专门支持；云签名/TLS可能不兼容 | 分协议选择，不部署新代理 |

**推荐最小机制**：保留DownloadService→Task→现有Worker→BinaryExecutor→原CLI；在BinaryExecutor下载调用边界增加受信的执行隔离适配，交由运维预置的OS运行设施建立每Task的namespace、cgroup和受限盘。它仅启动现有argv并返回执行事实，不接用户请求、不新增业务队列/审批/下载实现。非下载执行器默认不受影响。

Linux网络namespace隔离网络栈，但不会自动施加出站白名单；隔离后还必须有宿主侧不可绕过的出口规则。[network_namespaces手册](https://man7.org/linux/man-pages/man7/network_namespaces.7.html)

### 3.1 出口与DNS约束

- 每Task只能到达一个运维受控出口；无host network、DB/Redis网络、Docker/宿主socket、其他Task namespace或可变路由权限。rootfs只读、无NET_ADMIN/NET_RAW、禁止提权/任意setns；地址族IPv4/IPv6都显式覆盖，不能遗漏IPv6绕行。
- 环境采用白名单，不继承Worker凭据、代理变量、no_proxy、云HOME配置；可信执行参数和临时凭据通过受控只读材料提供。禁CLI自动安装依赖/自更新，依赖须预装并认证。
- DNS只由可信出口解析，校验整个结果集及CNAME相关最终地址，拒绝私网/回环/链路本地/元数据/混合结果；使用获准结果建立实际socket，重新解析就重新校验。网络层同时拒绝任意私网/host/其他namespace目的地。
- HTTP由可信协议出口验证每个新请求和Location，禁止协议降级及未经允许的端口。域名白名单不等于实际IP约束；原始IP请求也走同样策略。
- **HTTPS取舍**：透明转发/普通CONNECT只能看到目的主机/连接和密文字节，不能证明加密内逐跳URL规则。若无法在现有客户端禁用自动redirect并可信逐跳校验，或没有经批准、兼容证书/签名的协议出口，HTTPS继续BLOCKED。不能默默安装MITM根证书，也不能宣称只用namespace就解决全部redirect要求。
- HTTP(S)代理/原始socket直连尝试都由任务边界拒绝；“强制代理”由网络拓扑保证，不由模型或CLI自愿遵守。出口故障必须拒绝，不直连fallback。

### 3.2 FTP特有约束

控制连接与PASV/EPSV数据连接全部通过同一受控边界；禁止主动模式外连。只接受与获准控制端点相符的数据地址和明确受控的被动端口范围，不能信任服务器返回的任意IP/端口。普通HTTP代理是否能代理FTP、是FTP-over-HTTP还是原生FTP均须实测，不能写成通用兼容结论。

Python ftplib枚举必须迁入同一受限执行上下文；否则即使aria2/wget隔离也遗漏网络路径。该移动只调整原枚举位置，不新增FTP下载器；无法迁移/约束前，FTP递归继续BLOCKED。仅列举文件同样计入网络预算和任务超时。

## 4. 网络与磁盘硬预算

### 4.1 计量口径先于实现

分别记录：任务边界实际接收的网络字节、获准传给任务的字节、文件逻辑长度、文件系统实际分配块与inode数。重试/重复Range/失败响应/TLS开销按网络口径计入；压缩、转换和临时文件按盘口径计入。两者不能互相推算。

网络硬限制必须在流量到达任务前同步消费同一Task的共享额度，覆盖所有socket、后代、文件、DNS/FTP枚举及重试，余额不足立即停止准入并关闭连接。不能只轮询接口计数再kill。选定内核packet级实现时，必须证明多核并发原子扣减、分片/GSO/GRO处理、计量点和单包边界，明确包含头部的口径；未测前不宣称零超调。若使用协议出口，可限制解密body量，但还需独立统计/约束TLS和失败流量。

**边界限制**：不能保证恶意远端在Task停止后不继续向宿主发送数据；“Task可消费/边界可放行字节硬限”不等于互联网链路/云账单总接收量硬限。如果项目要求后者，需上游提供商配额/断路能力，否则该要求保持BLOCKED。

不在本报告指定未经实测的nft/BPF规则或代理产品，不提供一个貌似可执行却未验证的防火墙脚本。候选底座可兼容现有CLI，并不证明硬预算已实现。

### 4.2 磁盘隔离

优先评估运维现有XFS project quota：每Task使用独立project tree，同时限制分配块与inode；输出、TMPDIR、HOME、checkpoint/cache、fasterq临时目录全部位于该树。根文件系统/依赖只读，无其他可写挂载；单独的tmpfs也必须限容并记入独立内存/总存储预算。禁止通过其他project、硬链接、挂载、Docker socket或额外临时路径逃逸。现有存储若是NFS/其他文件系统，不能假设XFS策略可直接使用，需选其可证明的等价硬配额或保持BLOCKED。

XFS project quota能够约束目录树；实际支持须由文件系统类型、挂载及quota状态验证。[xfs_quota手册](https://man7.org/linux/man-pages/man8/xfs_quota.8.html)

稀疏文件逻辑长度和块占用不同；按文件逻辑总量另设验证策略，不能把block quota当成逻辑字节上限。RLIMIT_FSIZE仅适合补充单文件限制；cgroup IO带宽不等于磁盘容量，memory.max也不替代盘配额。

### 4.3 超额、取消、Worker终止和空间耗尽

| 场景 | 必要行为 | 当前缺口 |
|---|---|---|
| 网络额度耗尽/未知Content-Length/撒谎长度 | 以实际计量拒绝更多流量，取消全部连接/后代，保留原因与计量 | 无可信计量/执行器接线 |
| 磁盘EDQUOT/ENOSPC/inode不足 | 写入由FS拒绝；Task不得SUCCESS；保留部分文件待对账 | 无任务硬quota，CLI错误传播需实测 |
| 人工/Agent取消 | 现有授权校验→任务范围停止→确认cgroup无存活进程→文件对账 | 当前DB CANCELLED不是停止确认 |
| Worker SIGKILL | 独立于Celery进程的受信OS监督器按deadline/租约撤销出口并停止任务组 | 父进程退出/pgid本身不够 |
| 监督器重启 | 默认阻断新出口，扫描受控scope及租约，隔离未能证明归属的scope，不盲目重启下载 | 需与S4持久状态对账设计衔接 |
| 续传/重试 | 复用同Task受控scope/持久余额；不得通过重启重置额度 | 当前无预算ledger，S4依赖 |
| 转换/压缩/解压 | 下载、fasterq、gzip及临时文件同scope；沿用Dataset解压限制，不新造解压器 | 真临时路径/峰值与崩溃清理未验 |

cgroup可组织后代进程并使用cgroup.kill停止整个树；先建立scope再spawn，避免“进程先运行后迁入”窗口。kill后还需确认为空。memory/pids资源限制与退出观察均为补充，不代表网络/磁盘预算。[cgroup v2官方文档](https://docs.kernel.org/admin-guide/cgroup-v2.html)

监督器使用运维现有服务管理设施；不允许普通下载进程获得特权。没有已授权的scope操作接口时，不给Worker加root或NET_ADMIN作为捷径。

## 5. 人工与Agent准入检查

源码检查结论：

- `describe_transport_admission`当前只有服务端静态拒绝，没有可信运行证书存储/消费实现；caller_kind只是描述标签，不能授权。
- `require_download_runtime`消费来源协议集合的拒绝，单独改变全局switch仍不能通过；Service与Worker双重调用。未知协议继续拒绝。
- 人工REST依赖CurrentUserId与require_human_or_confirmation；AgentToolGateway由可信会话/项目上下文构造身份并受WRITE_RUNTIME_ACCEPTED及scope检查；不把模型给的caller_kind或user_confirmed当身份。
- 当前两者都BLOCKED；尚无可信协议认证后分别放行的完整实现，不应称“人工已恢复”。

待实施的最小差异控制应来自服务端持久/运维受控状态：`environment + worker digest + tool hashes + protocol + egress/quota policy revisions + expiry + permitted caller channels`。模型/前端不能上报证书或开关。服务端从JWT路由/可信委托/持久Task派生caller；Worker重新核持久Task来源和证书，不信任queued payload中的caller字符串。人工和Agent分别有准入项；Agent还需已有scope和人类确认消费。批准一条人工路径不自动批准Agent路径。

本轮不新增证书API/审批表/任务表。如何复用现有运维配置或持久记录，需结合可信发布来源与S4对账评审；缺实现时维持静态拒绝，不用Boolean声明“已认证”。

## 6. 最小修改范围（后续，尚未实施）

1. 下载专用ExecutionContext扩展受信scope引用、deadline和预算引用；BinaryExecutor交给预置OS设施启动现有argv，不从模型收shell/namespace/路径参数。默认普通任务行为不变。
2. Worker把FTP枚举、EBI进度访问、所有CLI与后代纳入同scope；收窄进度服务可达范围，敏感key只用于受控通道。取消/失败/退出等待真正停止后再调用原FileRegistry/Dataset链。
3. 运维提供每Task隔离/唯一出口、真实计量硬限、受限写盘与独立生命周期；只挂所需只读工具/输入和一个Task写目录，绝不挂Docker socket/Worker凭据。
4. Service/policy/Gateway接可信服务端认证与caller，不改变原确认系统；预算原子预留/结算/恢复与S4设计对齐，不新增第二个任务系统。
5. 每个工具版本独立兼容测试。没有可信出口、TLS逐跳、FTP数据约束或硬quota的后端继续拒绝；不一次开放全部来源。

上述改动需先确定并验证宿主设施，不能在当前受限环境中部署猜测实现。

## 7. 本轮测试与证据

证据目录 `evidence/download-s3-runtime-enforcement/`：HEAD/status/递归子模块快照、宿主只读观察、isolated-tests.txt。本轮未修改测试替身或生产开关。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib \
.venv/bin/pytest tests/unit/test_download_s3_closure.py \
 tests/unit/test_lifecycle_download_security.py \
 tests/unit/test_download_worker_protocol_gate.py -q -m 'not quarantine'
```

结果：**98 passed，1存量Pydantic warning，PASS_ISOLATED**。证明现有语法/策略拒绝、修改请求重验、全局开关不能自证、Worker拒绝等本地边界；不证明DNS、网络字节、磁盘quota、真实取消或运行兼容。S1登记249项联合记录属于上轮，不冒充本轮重跑。真实运行测试均NOT_TESTED。

续轮完成审计（2026-10-16）：重新读取附件四阶段要求、活动架构和最新Closure报告，并核对当前 `infrastructure/execution/binary.py`、Worker三来源与FTP枚举门禁、Compose挂载、EBIDownload源码、Service、REST及Gateway。以上同一命令再次执行，结果 **98 passed，1 warning，0.49s**；不是新增用例或累计计数。当前仍无获授权的隔离Worker入口，未再次连接Docker socket；§1.2的socket拒绝及工具哈希是既有观察，不冒充本次实时观察。未执行CLI、下载、生产迁移或网络变更。修正§1.1挂载描述后，本文九项交付要求均有对应章节；真实认证与enforcement保持明确未完成，采用用户指定的环境不可用交付分支，不将G3阻断误报为运行通过。

## 8. 授权隔离环境验收步骤

环境尚未提供，因此以下是待执行步骤，不是可在生产复制的部署命令。

1. 指定非生产用户/项目、允许目标、最多测试流量/磁盘/时长、清理归属；提供独立Worker/DB/Redis及只读运维访问。不得借当前生产账号或用户文件测试。
2. 运维采集实际容器digest、UID/caps、工具version/hash/help、依赖、mount/cgroup、DNS/IPv4/IPv6/代理拓扑和FS/quota。使用既有inspect_download_runtime.py SOURCE_ONLY后合并授权观察；清单一致仍不是认证通过。优先验证工具存在、托管依赖禁止自安装和TLS/云签名兼容。
3. 由运维在专用隔离宿主预置拟选设施；先以不含CLI的受控探针证明无法访问宿主/DB/Redis/Docker/私网与替代代理，覆盖IPv6、socket直连、DNS变化和出口故障；探针失败不启动下载测试。
4. 选最小受控HTTP文件验证首条后端，记录Task ID、scope、网络计量、盘配额及实际FileRecord。随后独立验证HTTPS逐跳策略、Range/多连接、chunked和无/假长度；不能用HTTP测试代替HTTPS/FTP。
5. FTP单独验证PASV恶意IP、EPSV端口、主动模式、目录递归/列表总量与枚举同scope。无法控制则仍BLOCKED。
6. EBIDownload分别验证aws/ftp及其wget/fasterq/压缩/进度路径。三云各用独立临时测试桶、最小权限凭据和锁定版本验证，未提供者标NOT_TESTED。
7. 在已批准小额度内构造累计超量、重复下载、临时文件膨胀、inode/块配额不足；核对硬停止点和最大可放行量。再测取消、Worker SIGKILL、监督器重启、恢复后余额不重置，确认无残留可联网进程。
8. 复验FileRegistry task_id/source/SHA/size/owner及原Dataset reconcile；部分/超额/取消不成为SUCCESS或科研READY。生成脱敏证据，认证关联到版本/策略/环境，不改生产开关。

所需证据必须包含观测点、单位、初末计数、Task/scope关联、停止原因、进程树为空证明、FS报告与文件hash；不能只贴CLI进度百分比。失败、丢日志或归属不明全部按待对账处理。

## 9. G3状态与S4准入建议

**G3 = PARTIAL_CODE / RUNTIME_BLOCKED。** 本次调查/设计交付完成，不代表enforcement代码或运行闭合。

阻断：真实Worker不可观察；CLI版本/三云兼容未知；不存在已验证的任务级唯一出口与流量硬限；TLS逐跳和FTP数据约束未定；FS能力/任务硬quota未知；父子进程取消及Worker死亡后的监督缺失；可信认证消费及预算恢复未实现。

S4依赖执行准入：**不通过**。可以在另获阶段授权后先设计预算持久化、Task独占目录和恢复契约，但不能因此开放传输或声称G3通过。本轮到此停止。

回滚/保护：本轮只新增本文和证据快照，无需业务回滚。保留全部历史Task、文件、FileRecord、Dataset和已有代码。没有部署、网络变更、真实下载、生产迁移、提交或推送；证据含部署内部路径，仅作为运维材料，不加入模型工具目录。
