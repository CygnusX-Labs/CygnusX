# 生物信息软件包目录

> 本目录由 Agent YAML 的 `package_catalogs` 自动选择并注入提示词。它提供候选包与用途，不是已安装清单：任何包都需要先用 `conda-meta-mcp` 查询当前可用的 conda 包名、channel 和版本，并以实际导入/CLI 输出为准。**沙盒根文件系统只读、不支持现场装包**（`micromamba`/`pip`/`install.packages()` 一律会失败），第三列的 `channel/包名` 只是供查询与提需求时引用；缺包时如实告知用户，并建议改选具备该能力的运行时或把依赖做进镜像。

<!-- package-catalog: genomics -->
##### 1 基因组学 / 序列分析

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `biopython` | FASTA/FASTQ/GenBank 解析、BLAST 接口、翻译与 motif | `conda-forge/biopython` |
| `pysam` | BAM/CRAM/SAM/VCF/BCF 读取与操作 | `bioconda/pysam` |
| `pyfaidx` | 快速索引读取 FASTA | 先查 conda 坐标 |
| `pybedtools` | BED/GTF/GFF 区间操作 | `bioconda/pybedtools` |
| `pysamstats` | BAM 文件统计信息 | `bioconda/pysamstats` |
| `cyvcf2` | 高性能 VCF/BCF 解析 | `bioconda/cyvcf2` |
| `mappy` | minimap2 的 Python 接口，长读序列比对 | `bioconda/mappy` |

<!-- package-catalog: rnaseq -->
##### 2 转录组学 / RNA-seq

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `pysam` | BAM 基础操作 | `bioconda/pysam` |
| `HTSeq` | 计数矩阵生成 | `bioconda/htseq` |
| `rpy2` | 在 Python 中调用 R/Bioconductor | `conda-forge/rpy2` |
| `pydeseq2` | Python 差异表达分析 | 先查 conda 坐标 |
| `gseapy` | GSEA / ORA 富集分析 | `bioconda/gseapy` |

<!-- package-catalog: scrna -->
##### 3 单细胞分析

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `scanpy` | 单细胞分析主框架 | `conda-forge/scanpy` |
| `anndata` | 单细胞数据格式 | `conda-forge/anndata` |
| `mudata` / `muon` | CITE-seq、scATAC+RNA 等多模态分析 | 先查 conda 坐标 |
| `scvi-tools` | scVI、totalVI、DestVI 等深度学习模型 | `conda-forge/scvi-tools` |
| `scarches` / `celltypist` | 参考映射与细胞类型注释 | 先查 conda 坐标 |
| `squidpy` | 空间转录组分析 | `conda-forge/squidpy` |
| `decoupler` / `omnipath` | 通路活性与信号网络推断 | 先查 conda 坐标 |
| `scikit-misc` | Scanpy 绘图等依赖 | `conda-forge/scikit-misc` |

<!-- package-catalog: r-bio -->
##### R / Bioconductor 统计与单细胞

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `Seurat` / `SeuratObject` | R 单细胞分析与对象管理 | `conda-forge/r-seurat` |
| `SingleCellExperiment` / `scater` / `scran` | Bioconductor 单细胞对象、QC 与归一化 | 先查 bioconda 坐标 |
| `Harmony` / `SeuratDisk` | 批次整合、Seurat 与 H5AD 转换 | 先查 conda 坐标 |
| `DESeq2` / `edgeR` / `limma` | 差异表达与 voom 分析 | 先查 bioconda 坐标 |
| `clusterProfiler` / `org.Hs.eg.db` / `org.Mm.eg.db` | 富集分析与物种注释 | 先查 bioconda 坐标 |
| `tximport` | 转录本定量汇总 | 先查 bioconda 坐标 |
| `pheatmap` / `RColorBrewer` | R 可视化 | 先查 conda 坐标 |

R 包可用性以 `Rscript -e "library(<Pkg>); packageVersion('<Pkg>')"` 实际验证。若目录或查询结果中没有可用 conda 包，如实说明该环境未预装，不得绕过协议。

<!-- package-catalog: epigenomics -->
##### 4 表观遗传学 / 染色质

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `pyBigWig` | BigWig/BigBed 文件读写 | `bioconda/pybigwig` |
| `pybedtools` | BED 区间操作 | `bioconda/pybedtools` |
| `episcanpy` | 单细胞表观遗传分析 | 先查 conda 坐标 |
| `MACS3` | ChIP-seq/ATAC-seq peak calling | `bioconda/macs3` |
| `deepTools` | 信号可视化与质控 | `bioconda/deeptools` |
| `hicexplorer` / `cooler` | Hi-C 数据分析与 `.cool` 操作 | 先查 conda 坐标 |

<!-- package-catalog: proteomics -->
##### 5 蛋白质组学 / 结构生物学

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `biopython` / `biotite` | PDB、序列、结构与进化分析 | 先查 conda 坐标 |
| `mdanalysis` / `mdtraj` | 分子动力学轨迹分析 | `conda-forge/mdanalysis mdtraj` |
| `openmm` / `pdbfixer` | 分子动力学模拟与结构修复 | 先查 conda 坐标 |
| `prody` / `nglview` | 结构动力学与交互式分子可视化 | 先查 conda 坐标 |
| `py3Dmol` | Jupyter/网页分子结构可视化 | 先查 conda 坐标 |

<!-- package-catalog: microbiome -->
##### 6 微生物组学 / 宏基因组

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `qiime2` | 16S 与宏基因组分析平台 | 先查 QIIME2 channel 坐标 |
| `scikit-bio` | 微生物组统计与距离矩阵 | `conda-forge/scikit-bio` |
| `biom-format` | BIOM 格式处理 | `bioconda/biom-format` |
| `humann` / `metaphlan` | 宏基因组功能与物种注释 | 先查 bioconda 坐标 |
| `kraken2` / `bracken` | 宏基因组分类 | 先查 bioconda 坐标 |

<!-- package-catalog: variants -->
##### 7 变异分析与群体遗传

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `cyvcf2` | 高性能 VCF 解析 | `bioconda/cyvcf2` |
| `scikit-allel` / `sgkit` | VCF、Zarr、PCA 与群体遗传分析 | 先查 conda 坐标 |
| `tskit` / `msprime` / `stdpopsim` | 树序列和群体遗传模拟 | 先查 conda 坐标 |

<!-- package-catalog: phylo -->
##### 8 系统发育 / 进化

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `ete3` | 系统发育树可视化与操作 | 先查 conda 坐标 |
| `dendropy` / `biopython` | 树计算与 Newick/Nexus/PhyloXML 解析 | 先查 conda 坐标 |
| `toytree` / `phyluce` | 树绘图与 UCE 分析 | 先查 conda 坐标 |

<!-- package-catalog: enrichment -->
##### 9 通路富集与功能注释

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `gseapy` | GSEA / ORA 富集分析 | `bioconda/gseapy` |
| `goatools` / `enrichr` | GO 与 Enrichr 接口 | 先查 conda 坐标 |
| `reactome2py` / `keggutils` | Reactome、KEGG 接口 | 先查 conda 坐标 |
| `clusterProfiler` | R/Bioconductor 富集分析 | 见 R / Bioconductor 分类，并先查询验证 |

<!-- package-catalog: io -->
##### 10 数据格式与 IO

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `anndata` | 单细胞 AnnData 格式 | `conda-forge/anndata` |
| `zarr` / `xarray` | 大规模 N 维数组与带标签数据 | `conda-forge/zarr xarray` |
| `h5py` / `pyarrow` | HDF5、Parquet 与 Arrow 数据读写 | `conda-forge/h5py pyarrow` |
| `tiledb` | 基因组区间数据库 | 先查 conda 坐标 |
| `pydantic` | API/配置数据模型验证 | `conda-forge/pydantic` |
| `fsspec` / `s3fs` | 本地与对象存储文件系统接口 | 先查 conda 坐标 |

<!-- package-catalog: visualization -->
##### 11 生信专用可视化

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `matplotlib` / `seaborn` / `plotly` | 静态与交互式统计图表 | 以当前运行时清单为准；缺失时先查询 |
| `bokeh` / `altair` | 交互式网页与声明式可视化 | 先查 conda 坐标 |
| `pygenometracks` | 基因组浏览器式轨道图 | 先查 bioconda 坐标 |
| `karyoploteR` / `circlize` | R 染色体核型图与 circos 圈图 | 先查 conda 坐标 |
| `pyCircos` | Python circos 图 | 先查 conda 坐标 |

<!-- package-catalog: machine-learning -->
##### 12 生信机器学习 / 深度学习

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `scvi-tools` / `scarches` / `celltypist` | 单细胞 VAE、参考映射与分类 | 先查 conda 坐标 |
| `scikit-learn` | 经典机器学习 | 以当前运行时清单为准；缺失时先查询 |
| `xgboost` / `lightgbm` | 梯度提升分类与回归 | 先查 conda 坐标 |
| `pytorch` | 深度学习框架 | 先查 CUDA/CPU 兼容包坐标 |
| `transformers` / `fair-esm` / `bio-embeddings` | 生物序列预训练模型与嵌入 | 先查 conda 坐标 |

<!-- package-catalog: network -->
##### 13 网络与图分析

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `networkx` / `python-igraph` | 图与网络分析 | 先查 conda 坐标 |
| `omnipath` | 信号通路与蛋白互作网络 | 先查 conda 坐标 |
| `snap-stanford` | 大规模网络分析 | 先查 conda 坐标 |

<!-- package-catalog: cheminformatics -->
##### 14 化学信息学（Cheminformatics）

| 包 | 用途 | conda 坐标（channel/包名，供查询引用） |
|---|---|---|
| `rdkit` | 化学结构操作、分子描述符与 SMILES | `conda-forge/rdkit` |
| `openbabel` | PDB、SDF、SMILES 等格式转换 | 先查 conda 坐标 |
| `pubchempy` | PubChem 数据库接口 | 先查 conda 坐标 |
| `chempy` | 化学平衡与动力学计算 | `conda-forge/chempy` |
