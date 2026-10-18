# 下载 S2：协议契约与 Worker 来源清单

日期：2026-10-16。基于用户继续实施指令推进S2；S0/S1登记修复保留。不构建镜像、不重启Worker、不替换宿主程序、不迁移数据库、不提交/部署。阶段输入为两份统一下载实施文档、当前架构、S1报告与实际工作树。

## Stage S2 / Gate G2

- VERIFIED_CODE / PASS_ISOLATED：平台方法/协议拒绝、有效配置收紧、CLI方法兼容、来源清单、漂移与脱敏负例已实现并测试。
- BLOCKED_RUNTIME：没有新取得容器digest/程序版本/hash、真实传输、PG/Redis/队列/双Agent认证；离线清单固定不发布READY。
- **阶段兼容性仍需协调**：施工期间共享工作区另行加入了下载安全源码门禁、FTP限额、能力接口、UI写入禁用和存量测试修改。这些不在本轮S2的变更归属内，均已保留，不能把全部合并差异算作S2验收。当前人工下载也被这些新增门禁阻断，尚不能对任务书“人工既有入口可用”作完整通过声明。已发出并行会话协调问题；没有删除或反向开放该门禁。

## 基线与保护

开工分支/HEAD、dirty、diff stat、递归子模块状态在 `evidence/download-s2/{head,status,diff-stat,submodules}.txt`；修改前相关文件在before目录与before-sha256.json。保留S1已有成果、用户/Agent/前端与MCP脏文件，未reset/clean/stash。共享文件采用局部修改，现有写门禁与Handoff路径门禁保留。

红测试 `test_aspera_is_rejected_instead_of_silently_mapped` 在修改前失败：原DTO接受aspera，未抛ValidationError。日志 `evidence/download-s2/red-test.txt`；不是由测试替身模拟失败。

## 本轮实际实现

| 文件/函数 | 内容 |
|---|---|
| domain/download_contract.py | 唯一平台静态来源/方法/协议集合；SRA aws/ftp，直链http/https/ftp，三云scheme；稳定拒绝码；GEO需元数据解析；单accession输入，不宣称上游一定返回Run |
| application/schemas/download.py | 下载method类型对齐；不支持来源/方式/协议/provider返回稳定Pydantic错误type；未接线advanced/filter明确拒绝；accession规范化。未新增Agent任意URL工具 |
| tools/download/config.py | allowed_schemes只能收紧真实实现；YAML OR Settings功能判断抽为共享ensure_download_available；二进制优先级为显式YAML > 对应Settings/env > storage_path默认；拒绝相对路径或URL形态程序路径 |
| api/v1/downloads.py / DownloadService.submit / run_download | REST、内部Service、排队Worker再次核有效协议/配置；不支持配置在目录/Task/CLI副作用前拒绝；排队旧Aspera不静默改成FTP，Task失败带可核对reason |
| infrastructure/download/provenance.py | 只读源码/配置清单、严格运维观察Schema、锁文件/代码/镜像声明文件摘要、程序/路径/版本/方法/挂载漂移判定；不自授运行许可 |
| scripts/inspect_download_runtime.py | 生成SOURCE_ONLY清单；可显式合并可信运维观察；不执行程序/网络/容器/DB，不输出全环境；拒绝覆盖证据，错误不回显机密输入 |
| DownloadsView.vue / types/download.ts | 移除Aspera与失真最快宣传，单登录号说明，筛选未接入明确展示，云盘保留tab但禁提交；停用无接线高级字段与按钮 |
| builtin presets / 外部MCP downloads声明 / tools.yaml | 方法声明收敛aws/ftp，纠正GEO需解析和downloads目录。保留原确认/自批拒绝逻辑；不做S6完整多Agent接线验收 |
| infrastructure/mas/ebi.py | 旧旁路复用同一SRA方法集合，不继续允许已无CLI支持的Aspera；没有启用MAS |

S2没有改Worker Dockerfile、Compose、下载YAML或.env开关，没有安装任何程序或改变子模块。`download_security.py`、`download/policy.py`、`download_capability.py`、capabilities接口/动态前端与FTP递归限额等为期间另行出现的共享改动，完整审查属于后续协调整合，不在此表冒领。

## 方法/来源对账

| 输入/方法 | 平台契约 | 实际源码传输器 | 实际Worker证据 |
|---|---|---|---|
| 单SRR/ERR/DRR/SRX/SRP/PRJNA等ENA/SRA accession | 仅aws/ftp；源端解析可能无数据 | EBIDownload→ENA filereport；aws公共SRA→fasterq-dump/压缩，ftp→wget FASTQ/MD5 | UNKNOWN；不把格式接受当成真实数据支持 |
| GSE/GSM/GPL | DOWNLOAD_METADATA_RESOLUTION_REQUIRED | 先SOFT/ENA resolver；选Run或权威附件后现有import | UNKNOWN；不原样送CLI |
| aspera / prefetch / auto | DOWNLOAD_METHOD_UNSUPPORTED | CLI只有ftp/prefetch/aws/auto；平台暂仅接线aws/ftp | Aspera无对应实现；另外两项不自动暴露 |
| http/https/匿名ftp | 实现集合，可被allowed_schemes配置收紧 | aria2c；FTP目录有ftplib前置枚举 | 未做真实协议与出口认证 |
| ftps / file / s3直链 | DOWNLOAD_PROTOCOL_UNSUPPORTED | 不存在对应平台适配 | 不发布 |
| aliyun/volc/huawei及已有别名 | 对应oss/tos/obs，不匹配scheme拒绝 | ossutil/tosutil/obsutil cp | 每家独立UNKNOWN |
| S3/COS provider、云盘source | DOWNLOAD_PROVIDER_UNSUPPORTED / DOWNLOAD_SOURCE_UNSUPPORTED | 无通用远程拉取/分享提取器 | 不发布 |
| 样本/Run高级筛选 | DOWNLOAD_FILTERS_UNSUPPORTED | Rust CLI本身有过滤，但平台DTO/Service未接线 | 不把UI输入伪装有效 |

稳定错误码在REST的422 detail.type、Service ValidationError.code与Worker失败对账reason_code中可查。配置临时收紧时，之前创建的DTO不能绕过Service/Worker重验。URI语法不等于DNS/重定向/FTP数据连接硬策略，本轮不把S2策略冒充S3完成。

## 版本与构建来源

| 层级 | 可核实事实 | 不能推导的事实 |
|---|---|---|
| 平台子模块 | EBIDownload CLI crate1.4.0；SHA/Cargo.lock摘要见source-runtime-manifest-final.json | 不等于Worker实际二进制来自该提交 |
| 独立旁仓 | 历史审计Polariseq1.4.3 | 未自动部署/升级，本轮不引用其能力作为Worker事实 |
| 宿主 | 历史审计EBIDownload1.4.0及hash | 不是容器版本；本轮生成器不执行宿主CLI |
| CI/Worker声明 | 当前Dockerfile/Compose摘要已生成；现有外置工具路径保留 | 未取得CI构建日志/运行镜像digest |
| 真Worker | 未取得观察记录；清单scope=SOURCE_ONLY | UID、挂载、程序hash/version/help、Rust工具链均不能由源代码伪造 |

决策见 [ADR](../adr/download-transport-and-asset-registration.md)。保留外置工具方式，不自动向镜像安装最新版；若后续采用只读程序挂载或镜像打包，需独立版本/checksum/工具链与部署验收。当前共享数据盘可写挂载不证明binary目录只读。

## Runtime Manifest

规范：[运行来源清单v1](../contracts/cygnusx-download-runtime-manifest-v1.md)，[观察输入JSON Schema](../contracts/cygnusx-download-worker-observation-v1.schema.json)。实际SOURCE_ONLY产物在 `evidence/download-s2/source-runtime-manifest-final.json`，早期快照保留不覆盖。

即使运维填写一致的digest/version/hash/method/mount，也仅得到CONSISTENT_OBSERVATION；协议仍未验、release_ready=false，不改变任何feature或源码门禁。记录不能由模型/API上报，更不替代人类JWT确认。脚本只导出白名单配置，不导出token、S3密钥、FTP密码、CLI原始输出或全环境。

## 隔离验收与实际命令

- 后端当前联合回归：155 passed，1存量Pydantic warning。S2专用集合44 passed；日志 contracts-tests.txt / regression.txt。当前共享修改还修复了原存量DownloadService fixture并持续新增登记用例，因此这个集合不再是S1的103通过/5排除；不能把两轮数字相加。
- 前端专项3 passed：实际DownloadsView + jsdom；Naive组件、axios、路由是double。验证方法选择/请求参数、四tab/云盘禁用及运行关闭不提交；日志frontend-tests.txt。这不是浏览器/真实后端E2E，synthetic write_enabled=true仅用于表单契约用例，不开启后端门禁。
- 前端vue-tsc --noEmit：PASS，日志frontend-typecheck.txt。
- 聚焦Ruff与8个源码文件mypy(strict, follow-imports=silent)：PASS，日志ruff-focused.txt/mypy-focused.txt；迁移链：PASS，无新增迁移。
- 真实Worker/镜像、HTTP/FTP/云/SRA、PG/Redis、多Agent transport、真实科研E2E：NOT_TESTED/BLOCKED。没有构建、重启、真实下载、网络故障注入或生产GET探测。

后端命令（使用现有.venv，不更新锁文件）：

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True MPLCONFIGDIR=/tmp/cygnusx-matplotlib \
.venv/bin/python -m pytest \
 tests/unit/test_download_transport_contract.py tests/unit/test_download_provenance.py \
 tests/unit/test_download_worker_protocol_gate.py tests/unit/test_download_registration_contract.py \
 tests/unit/test_download_service.py tests/unit/test_dataset_import_handoff.py \
 tests/unit/test_dataset_geo_validation.py tests/unit/test_dataset_phase3.py \
 tests/unit/test_dataset_phase3_review.py tests/unit/test_dataset_gateway_phase3.py \
 tests/unit/test_phase0b_confirmation.py tests/unit/test_mcp_dual_surface_parity.py \
 -q -m 'not quarantine' -p no:cacheprovider
```

## 协调项、限制与回滚

施工期间增加的共享安全门禁 `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False` 已将Service、Worker和前端的人工执行也关闭；这些更改在本轮开始时不存在，已保留并发出会话协调问题。不将它们自动归因S2，不为保持测试通过而删除/打开门禁。需要其修改方明确责任与人工能力迁移策略，后续再验完整人工兼容；本轮三项jsdom契约只是当前行为证明。

S2尚不解决完整网络出站、传输字节硬停、配额预留、唯一目录、取消/重试对账、完整角色Catalog或真实运行门禁。不得以当前绿测试发布Agent下载。

回滚基于evidence/download-s2/before逐hunk评审；共享文件同时有其他变更，禁止整文件覆盖或git reset。新domain合同、provenance与Schema若已被共享改动引用，先解除依赖再回退，不能删除他方代码。保留用户Task/文件/登记记录与离线证据；不撤销S1成果，不执行数据库操作。下一步先完成并行修改协调，再按阶段检查S3/S4，不盲目启动真实运行验收。
