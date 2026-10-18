# Verified Claim Selection v1

首版只支持 `deg.tsv` 的有限单元格。选择字段是 Task、可选 Report、FileRecord、feature/gene 和受限 column；`value`、SHA、owner/project、verification_status 等可信字段禁止客户端提交。服务端读取受管字节，复核 M0 实际包含关系、FileRecord 生命周期、SHA、Observation/Report 版本和项目授权。

冻结 Claim 保留服务端读到的有限值、原始文件 SHA、Task/Version/Observation/Report 身份、执行定义可得性和缺口。`VERIFIED_VALUE` 只说明指定 SHA 下指定行列可读；`SUPPORTED_CLAIM` 首版只组合 `feature.column = value`。自由文本只可标为 `AI_INTERPRETATION`，不进入已验证结论。NA、非有限值、字节漂移、M0 外引用都拒绝或标 `NOT_VERIFIED`。
