# CountsDEGFlow

独立 gene×sample raw integer counts 入口，不调用或修改 RNAFlow。当前为隔离开发、默认隐藏的 Flow；R/DESeq2 与 Snakemake 小样本运行证明另见 Phase3 evidence，Worker/镜像/参考/监控发布验收仍不通过。不能把 TPM/FPKM/log/Series Matrix 当作输入。

与 FlowFrame v2.0 的适配：矩阵输入不运行仅适用于 FASTQ 的 seq_preprocessor、MD5 FASTQ 门或 short-read QC；以显式 SHA-256 input_manifest 作为统计 rule 的输入依赖，独立 sample QC、日志和 output manifest。该 specialization 尚未经 FlowFrame 全量认证，不冒称通用模板逐字兼容。保持未启用状态直至模板、rich-loguru logger、监控事件、镜像/Worker 和交付契约审查完成。

仅支持 `~ group` 与 `~ batch + group`，人工明确 reference/treatment；每组至少2个生物学重复、设计矩阵满秩且有剩余自由度。2重复结果明确标为 exploratory。DESeq2 Wald，不声称收缩 LFC。不执行远程脚本、eval 或用户自定义公式，不覆盖结果目录。

本地合成验证：`snakemake -s pipelines/CountsDEGFlow/snakefile --cores 1 --config analysisyaml=/tmp/<isolated-analysis.yaml>`。此命令不提交平台 Task；测试目录须是私有临时目录，输入由合成 fixture 产生。
