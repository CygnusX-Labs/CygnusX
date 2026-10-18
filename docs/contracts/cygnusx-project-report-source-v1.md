# Project Report Source v1

`ProjectReportSource` 是正式项目报告的冻结输入，不是 Task 报告。它绑定 owner/project、已发布 M0 `ProjectExportJob`、M0 manifest digest、冻结 Claim selection digest、格式及受控模板/脱敏版本。`renderer_runtime=NOT_OBSERVED` 表示尚未认证生产渲染镜像。

客户端只提交 M0 job、Task/File/Report 行列引用和格式；服务端通过 `ProjectDeliveryService` 和 `ResearchClaimService` 重建全部可信字段。source digest 不允许在确认时被替换。HTML/PDF 文件只有真实登记、回读 SHA/size 后才能使 Job ready；PDF 缺失使用 `PDF_NOT_GENERATED`，保留有效 HTML。

旧 `ReportModel`、`ReportGenerationJobModel`、`ReportSnapshotModel` 的 Task-first 约束不变。项目报告 Job 为追加式身份，旧 Report/Job/Manifest/ZIP 不原地更新。M1 必须由用户随后明确创建新 ProjectExportJob，不能形成报告到自身最终 ZIP 的摘要环。
