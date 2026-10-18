# 下载运行来源清单 v1

状态：S2 实现的运维离线契约；不是 Agent-facing 能力目录、生产认证结果或部署配置。生成器为 `scripts/inspect_download_runtime.py`，Worker 观察输入 Schema 见 [JSON Schema](cygnusx-download-worker-observation-v1.schema.json)。

## 来源与信任边界

默认 `SOURCE_ONLY`，仅读取当前主仓/下载子仓 SHA、dirty、Cargo/uv 锁文件及 Worker Dockerfile/Compose 的 SHA-256、CLI crate 声明版本和白名单有效配置。不连接 Docker、不读取全量环境、不执行下载程序，不从宿主工具版本推断容器能力。内部二进制路径与挂载只存运维产物，不通过 Agent Gateway 暴露。

显式提供 `--worker-observation` 时，输入必须由获授权的运维在隔离 Worker 采集。它包含 source/downloader SHA、实际 Worker 代码摘要、镜像 digest、非 root UID/GID、Rust 构建工具链证据、二进制 version/hash/help 摘要、methods 与挂载。Schema 拒绝额外字段；禁止放凭据、环境快照、原始 help/stdout 或私有URL。CLI 在校验失败时只输出固定错误，不回显输入或堆栈，拒绝超过1MiB的输入文件。

观察记录是受信审计输入，而非密码学签名；脚本不能证明填写者诚实，不能由前端或模型提交。生成器不消费确认、不改变任何开关。即使所有观察字段一致，也只报告 `CONSISTENT_OBSERVATION`，`runtime_status=BLOCKED / release_ready=false` 固定保留。真实协议、PG、Redis、身份与科研链仍需 DL-RG01–15；本契约不产生 PASS_RUNTIME。

## 输出字段

| 字段 | 语义 |
|---|---|
| schema_version | `cygnusx.download_runtime_manifest.v1` |
| recorded_at / scope | UTC采集时间；SOURCE_ONLY或SOURCE_WITH_OPERATOR_OBSERVATION |
| source | 主仓/下载子仓SHA与dirty、crate版本、Cargo.lock/uv.lock/Worker Dockerfile/Compose摘要 |
| declared | 平台方法与协议、有效allowed_schemes、未实现项、每来源依赖程序；不是运行支持证明 |
| configuration | YAML/Settings路径优先级、存储根、Web/Worker挂载变量、Worker声明UID与未知/实测UID；仅运维可读 |
| worker_observation | 未提供时null；可信运维记录严格按独立Schema校验 |
| worker_provenance_state | UNKNOWN / CONFLICT / CONSISTENT_OBSERVATION；只做内部一致性核对 |
| runtime_status / release_ready | 本生成器固定BLOCKED / false，不能作为执行批准来源 |
| reason_codes | 未取得Worker证据、代码/路径/版本/方法漂移、程序缺项、挂载/存储根问题、协议未验与源码写禁 |

## 程序依赖与平台边界

| 来源/方法 | 实际调用程序 | 源码可见但未对平台开放 |
|---|---|---|
| sra.aws | EBIDownload、SRA公共镜像获取、fasterq-dump、Rust压缩 | CLI prefetch/auto不自动成为平台可选方法 |
| sra.ftp | EBIDownload解析ENA→wget -c下载FASTQ/MD5 | Aspera无对应CLI方法，明确拒绝 |
| direct_link http/https/ftp | aria2c；匿名FTP目录先Python ftplib | FTPS、URL内账号密码不支持 |
| cloud_storage | OSS/TOS/OBS对应ossutil/tosutil/obsutil | 通用s3://、COS、云盘分享均未实现 |
| GEO | SOFT/ENA resolver→显式Run/权威附件 | 不把GSE/GSM原样当成可直接下载的SRA Run |

当前支持集合由 `domain/download_contract.py` 定义。下载配置allowed_schemes只能收紧http/https/ftp，不能通过添加字符串发明新传输器。REST、Service、排队Worker均重新检查；YAML功能开关与对应Settings/env保持原有OR语义。Agent源码写禁独立存在。

二进制配置优先级：显式下载YAML值 > 对应Settings/env二进制变量 > storage_path派生默认值。aria2c缺省`/usr/bin/aria2c`；配置必须为绝对文件路径。当前YAML写死路径依然覆盖env，脚本如实展示，不擅改宿主程序或挂载。

## 使用与采集

```bash
# 当前工作树来源清单；输出文件必须不存在
uv run python scripts/inspect_download_runtime.py --output /tmp/download-source-manifest.json

# 仅在运维已获隔离环境授权并采集观察文件后使用；不会执行观察中的程序
uv run python scripts/inspect_download_runtime.py \
  --worker-observation /tmp/approved-worker-observation.json \
  --output /tmp/download-source-and-worker-manifest.json
```

运维后续需要独立采集：镜像不可变digest和构建日志、容器内实际UID/GID/挂载、EBIDownload与各依赖version/hash/help摘要、下载Task消费的实际代码hash。比对容器与宿主文件内容及共享挂载；Web的CYGNUSX_DATA_ROOT与Worker的WORKER_SHARED_DATA_DIR变量名不同，同目标路径不能证明相同物理文件。

现有共享盘挂载并没有证明binary子目录只读。观察不包含覆盖该程序路径的只读挂载时，报告BINARY_MOUNT_NOT_READONLY；选择该模式的部署变更须另行评审。代码HEAD相同但bind-mounted下载Worker内容不同，会由worker_code_sha256判为漂移。

## 失败与回滚

只读工具无DB/Queue/网络副作用，拒绝覆盖已有证据。`DOWNLOAD_MANIFEST_INVALID`仅代表输入/配置格式或读取失败。删除本轮自行生成的离线产物不改变平台；不得因此删除用户文件/Task或替换历史证明材料。Schema变更需版本化，不能把人工填写的观察记录接到模型自批通道。
