# ProjectDeliveryManifest v1

状态：代码及隔离实现；真实 PostgreSQL / Celery / 对象存储 / 浏览器验收未完成。机器契约：[JSON Schema](cygnusx-project-delivery-v1.schema.json)。

`cygnusx.project_delivery.v1` 是项目级引用及字节清单，不是第二种 ReportSnapshot，也不是科学复现证明。摘要使用 `sorted_utf8_json.v1`：Python JSON、排序键、UTF-8、不转义 Unicode、紧凑分隔符、禁止非有限数字。服务端在冻结前排序 UUID 选择、文件路径、规范化引用及缺口；数组顺序参与摘要，不执行 Unicode NFC 或数字等价折叠。跨语言消费者消费服务端摘要，改变规范必须升级版本。

`manifest_digest = SHA256(canonical(manifest))`；摘要和 manifest 作为 envelope 存入 `ProjectDeliveryManifest.json`。项目、owner、实际选定 Task、报告 ID/版本/parent/snapshot/observation 关联、引用、文件、缺口和策略版本均参与摘要。时间不混入该内容摘要；请求/创建时间保存在 Job 行。摘要不是签名或授权票据。

`files` 只声明实际包含字节，每项有 POSIX 相对路径、source_kind/source_id、Task、大小及 SHA-256。包内目录采用analysis/report顺序号，真实稳定ID保存在清单引用中，不把宿主路径、原始参数、聊天、日志或凭据写入清单。`references` 分别表达 reference_only、missing、unverified、excluded；关联状态与包内字节完整性分开。历史无项目 FK 的 Task 不枚举为项目成员，保留覆盖缺口，不按路径/名称/时间补录。

`selection.kind` 为 evidence / results / reproduction_materials；默认 evidence。空 Task/Report 选择表示预览时当前有界可信集合；冻结后的具体文件和引用不再扩展，Worker 不因后来新增报告而补入。results 额外选择已登记、明确 Task、当前指纹 verified、允许后缀的小型结果。reproduction_materials 保存已有证据、快照及输入/环境缺口引用，不恢复历史执行，不复制原始输入。FASTQ/BAM/CRAM 等不进入自动结果收集；既有单任务 ZIP 也限定已知报告/快照/README/Manifest 成员。

实际 ZIP 包含 files 列出的文件，以及 `ProjectDeliveryManifest.json`、`checksums.sha256`。后两者不加入 files，避免自引用；checksums 覆盖所有 payload 和 Manifest，排除自身。归档采用 ZIP_STORED、固定 ZIP 时间和排序成员；逐文件及最终 ZIP SHA 都核验。验证器拒绝重复成员、额外成员、不规范路径、目录、链接、加密成员、重复 JSON 键、错误大小/SHA 和校验清单覆盖差异，检查展开预算，不解压执行内容。

首版默认上限：500 payload、单文件16MiB、payload合计64MiB、最终 ZIP 80MiB。Settings 允许下调；payload/file 硬上限仍为64/16MiB，archive硬上限128MiB。不直接调用512MiB单任务内存 Builder 生成项目包。有限内存实现不是无限流式导出；更大项目拒绝 EXPORT_LIMIT，不能静默截断。

缺报告/快照可 partial；预览后已纳入的文件消失、漂移或授权变化必须失败，不能悄悄换范围。`reproduction_status=NOT_RUN`。历史关联覆盖未知和执行环境未认证仍是缺口，首版一般保持 partial；字节完整不解锁复现。

包内 `verify_project_delivery.py` 只依赖 Python 标准库：`python verify_project_delivery.py project-delivery.zip`。在线下载还与鉴权 Job 的 ZIP SHA 比较。离线 Manifest/校验和可以一同被攻击者重写，因此不提供签名真实性或科学正确性结论。
