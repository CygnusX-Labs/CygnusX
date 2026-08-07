# ATAC-seq 知识库资源目录

本目录是 OmicHub ATAC-seq 知识库的文件源。Markdown 正文会由
`scripts/import_atacseq_knowledge.py` 全量同步到 `atacseq` AI 检索库；PDF 和图片保留为
`/docs-static/knowledge/atac-seq/` 下的静态证据与下载附件。

## 核心文档

- [ATAC-seq 原理、实验与分析流程](ATAC-seq.md)
- [Chromatin Accessibility](<Chromatin Accessibility.md>)

## PDF 资料

- [ATAC-SEQ](file/ATAC-SEQ_lytlsHKBI3.pdf)
- [ATAC analysis](file/ATAC-analysis_E01C5eeyzq.pdf)
- [ATAC-seq upstream analysis](file/ATAC-seq%20upsteam-analysis_BL8NUSbvJL.pdf)
- [ATAC-seq library](file/ATAC-seq-library_IWIcEwhsuN.pdf)
- [ATACSeq Pipeline](file/ATACSeq%20Pipeline_93Woz7CDR_.pdf)
- [Chromatin Accessibility Profiling and Data Analysis](<file/Chromatin Accessibility Profiling and Data Analysi.pdf>)
- [Chromatin accessibility profiling by ATAC-seq 1](file/Chromatin%20accessibility%20profiling%20by%20ATAC-seq_-L1C.pdf)
- [Chromatin accessibility profiling by ATAC-seq 2](file/Chromatin%20accessibility%20profiling%20by%20ATAC-seq_D1Xn.pdf)
- [Transposition of native chromatin](<file/Transposition of native chromatin for fast and sen.pdf>)
- [Building library](file/building-library_qDXJ-SE98N.pdf)
- [Downstream analysis](file/downsteam-analysis_xnComJZQ4x.pdf)
- [Nucleosome](file/nuclesome_qT7ajGF73N.pdf)

## 图片资料

- [ATAC-SEQ overview 1](image/ATAC-SEQ_s0hN60_H10.png)
- [ATAC-SEQ overview 2](image/ATAC-SEQ_vro37-wfgY.png)
- [ATAC analysis](image/ATAC-analysis_uYEhuUDs0E.png)
- [ATAC-seq upstream analysis](image/ATAC-seq%20upsteam-analysis_WMhULSZ_6H.png)
- [ATAC-seq library 1](image/ATAC-seq-library-01-01_jlbQSJ6C6x.png)
- [ATAC-seq library 2](image/ATAC-seq-library-01-02_1fc3ZduzL3.png)
- [Basic units of chromatin structure](image/Basic_units_of_chromatin_structure_6SH00q_mL3.png)
- [Chromatin accessibility](image/Chromatin%20accessibility_r_qX_4WNxU.svg)
- [Insert size distribution](image/Insert%20Size%20Distribution_phroTit4ck.svg)
- [OCT4](image/OCT4_7N8IA-H4kO.svg)
- [PTC](image/PTC_-BHoo0Kkrk.png)
- [Building library](image/building-library_OAZVwh60B7.png)
- [Downstream analysis](image/downsteam-analysis_G6MMdSU85h.png)
- [Histone](image/histone_PsCDUSwSyy.png)
- [Image ANxkwKHI4I](image/image_ANxkwKHI4I.png)
- [Image B0-6TGtgVs](image/image_B0-6TGtgVs.png)
- [Image C8r7qRcmW6](image/image_C8r7qRcmW6.png)
- [Image HQUzNmet4g](image/image_HQUzNmet4g.png)
- [Image ShHxkXcErv](image/image_ShHxkXcErv.png)
- [Image WenVG75lKU](image/image_WenVG75lKU.png)
- [Image eNNaHNIZY2](image/image_eNNaHNIZY2.png)
- [Image rAIBEJu2c7](image/image_rAIBEJu2c7.png)
- [Image zEcibdmqwe](image/image_zEcibdmqwe.png)
- [Nucleosome chromatin](image/nuclesome-chr_hSFeidbPoS.svg)

## 维护规则

- 新增 Markdown 会在下次导入时自动成为独立知识文档。
- 新增附件必须从本目录中的至少一篇 Markdown 链接，避免形成不可发现的孤立资源。
- 相对链接在入库时改写为 `/docs-static/knowledge/atac-seq/...`，源文件保持不变。
- PDF 与图片不直接做文本索引；可检索信息应同时整理到 Markdown 正文。
