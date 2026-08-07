# RNA-seq

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 EST & microarrays](#11-EST--microarrays)
  - [1.2 RNA-seq ](#12-RNA-seq-)
  - [1.3 RNA-seq  & mRNA  splicing  & non-coding RNAs & enhancer RNAs](#13-RNA-seq---mRNA--splicing---non-coding-RNAs--enhancer-RNAs)
  - [1.4 RNA-seq Platform](#14-RNA-seq-Platform)
    - [1.4.1 Short-read VS long-read](#141-Short-read-VS-long-read)
    - [1.4.2 short read sequence](#142-short-read-sequence)
    - [1.4.3 long read sequence](#143-long-read-sequence)
    - [1.4.4 Direct RNA-Seq & m^6A](#144-Direct-RNA-Seq--m6A)
  - [1.5 RNA-seq sequencing protocol](#15-RNA-seq-sequencing-protocol)
    - [1.5.1 building library method](#151-building-library-method)
      - [polyA enrichment](#polyA-enrichment)
      - [ribosomal RNA depletion](#ribosomal-RNA-depletion)
      - [1.5.1.3 strand-specific RNA-seq](#1513-strand-specific-RNA-seq)
      - [1.5.1.4 small RNA-seq ](#1514-small-RNA-seq-)
      - [spike-in (ERCC)](#spike-in-ERCC)
      - [UMI](#UMI)
  - [1.6 Normalization & RNA-seq](#16-Normalization--RNA-seq)
    - [1.6.1 ERCC](#161-ERCC)
    - [1.6.2 ERCC & lncRNAs](#162-ERCC--lncRNAs)
  - [1.7 ERCC & scRNA-seq](#17-ERCC--scRNA-seq)
  - [1.8 RNA-seq analysis pipeline](#18-RNA-seq-analysis-pipeline)
    - [1.8.1 Updata Bulk RNA-seq pipeline](#181-Updata-Bulk-RNA-seq-pipeline)
    - [Assemble transcripts de novo ](#Assemble-transcripts-de-novo-)
  - [1.9 Tumor microenvironment (TME)](#19-Tumor-microenvironment-TME)
  - [1.10 scRNA-seq](#110-scRNA-seq)
- [2 Source](#2-Source)
- [3 Reference](#3-Reference)

***

***Author***\*\* : JZHANG\*\*​

***Date***\*\* : 2025-10-12\*\*​

***Version***\*\* : \*\***`1.0v`**

***

在2006年之后受益于NGS技术的发展，基于二代测序的RNA-seq的转录本分析技术开始不断涌现，因此对于相`EST`(`Expressed Sequence Tag`)这样的技术不会在本文档中进行具体介绍啦

***

[Transcriptomics in the era of long-read sequencing.pdf](<file/Transcriptomics in the era of long-read sequencing.pdf> "Transcriptomics in the era of long-read sequencing.pdf")

## 1 Introduce

### `1.1 EST` & `microarrays`

![Fig. 1. Summary of cDNA cloning and expressed sequence tag (EST) sequencing  Fig. 1. Summary of cDNA cloning and expressed sequence tag (EST) sequencing  ](image/EST_1ljzadGalw.svg "Fig. 1. Summary of cDNA cloning and expressed sequence tag (EST) sequencing  Fig. 1. Summary of cDNA cloning and expressed sequence tag (EST) sequencing  ")

[Expressed sequence tags- alternative or complement to whole genome sequences?.pdf](<file/Expressed sequence tags- alternative or complement.pdf> "Expressed sequence tags- alternative or complement to whole genome sequences?.pdf")

> gsnap RNA-seq Analysis
>
> [ RNA-Seq workflow | Introduction to RNA-seq using HPC Introduction to RNA-seq using HPC https://hbctraining.github.io/Intro-to-rnaseq-hpc-gt/lessons/08\_rnaseq\_workflow.html](https://hbctraining.github.io/Intro-to-rnaseq-hpc-gt/lessons/08_rnaseq_workflow.html " RNA-Seq workflow | Introduction to RNA-seq using HPC Introduction to RNA-seq using HPC https://hbctraining.github.io/Intro-to-rnaseq-hpc-gt/lessons/08_rnaseq_workflow.html")

***

### 1.2 RNA-seq&#x20;

RNA-seq 是一种对单个细胞或者mix细胞组织在某一个状态下基因表达情况的整体记录(也可以说是对不同条件下基因表达情况的snapshot[^1])。由于能够对不同状态下细胞or组织基因表达情况进行快速记录，因此可以探索不同条件下的基因表达情况，从而为不同状态下细胞的不同命运或者表型，提供可能是基因表达情况角度的解释。

massively parallel cDNA sequencing, or RNA-seq[^2].

> 在RNA-seq 刚刚开始发展阶段其也被称为大量平行cDNA测序！

**summary RNA-seq**[^3]

![](image/Summary_of_RNA-Seq__2NcLCk7xC.svg)

**RNA-seq summary:**

> **RNA-seq  in silico**[^4]: 当完成高通量测序后需要将测序获得的序列经质量控制，*mapping* (对比到基因组)、*featurecount (exon 、CDS &  gene levels count)*、*DGE*、\*GO & KEGG Enrichment \*、*gene-fusion analysis* 、*splicing*。

> **RNA-seq  in vivo** : 当细胞or组织面临不同的环境后其基因组表达状态会发生不同的变化，基因中不同的外显子序列在mRNA 程序过程中会发生不同的可变剪切从而组合产生不同的基因表达序列(mature mRNA  sequence)，而RNA-seq 就是对这些成熟的mRNA进行测序。

> **RNA-seq  in vitro** : 为了获得不同条件下处理下细胞or组织基因表达情况，需要在体外对一定量的细胞或者不同的组织进行RNA提取，然后将不同长度的mRNA使用物理或者化学方法将其打断为特定长度范围的片段，然后使用特定的酶在其两端添加测序使用的adapter ，使用RT-RCR进行片段的扩增后使用高通量测序设备(NGS[^5]测序主要的测序方案是illumina公司的)进行高通量测序。

***

### 1.3 RNA-seq  & mRNA  splicing  & non-coding RNAs & enhancer RNAs

Broader applications of RNA-seq have shaped our understanding of many aspects of biology, such as by revealing the extent of mRNA splicing[^6]  and the regulation of gene expression by non-coding RNAs [^7]and enhancer RNAs.

> 随着RNA-seq技术的不断运用，在RNA-seq基础上慢慢发现了mRNA的可变剪切现象 & RNA中的非编码RNA!

![Frequency and relative abundance of AS isoforms in human genes Frequency and relative abundance of AS isoforms in human genes ](image/image_Ecoz_W8x_R.png "Frequency and relative abundance of AS isoforms in human genes Frequency and relative abundance of AS isoforms in human genes ")

![](image/non-codingrna_t6-_CLsn94.png)

Coding and non-coding transcripts are predominantly localized in the cytosol and nucleus, respectively, with a range of expression spanning six orders of magnitude for polyadenylated RNAs, and five orders of magnitude for non-polyadenylated RNAs.[^7]

> 编码和非编码转录本主要分别定位于胞质溶胶和细胞核中，多聚腺苷酸化 RNA 的表达范围跨越 6 个数量级，非多聚腺苷酸化 RNA 的表达范围跨越 5 个数量级。

Global transcriptomic and (epi)genomic advances have found that enhancers are pervasively transcribed into non-coding RNAs (ncRNAs), which are named enhancer RNAs (eRNAs).[^8]

> enhancers (启动子) → non-coding RNAs （enhancer RNAs ，eRNAs）

[Enhancers as non-coding RNA transcription units recent insights and future perspectives.pdf](<file/Enhancers as non-coding RNA transcription units re.pdf> "Enhancers as non-coding RNA transcription units recent insights and future perspectives.pdf")

***

### 1.4 RNA-seq Platform

\*\*Sanger \*\*→ **NGS** → \*\*Third generation sequencing \*\*

[Sequence & platforms (Sanger → NGS → long-read)](https://www.wolai.com/wwrLWuph43BpTLhJMzKhJN "Sequence & platforms (Sanger → NGS → long-read)") :  一代到三代测序技术的发展！

The library is then sequenced to a read depth of 10–30 million reads per sample on a high-throughput platform (usually Illumina).[^9]

> 标准short-read RNA-seq 测序量**10–30 M reads & 6G**的测序量就能够满足下游的分析需求！

Much of this method development has been achieved on Illumina short- read sequencing instruments, but recent advances in long-read RNA-seq and direct RNA sequencing (dRNA-seq) 12–14 methods are enabling users to ask questions not answerable with Illumina short-read technologies.

![](image/rna-seq-1-02-02_my_93SgR8w.png)

> 现阶段RNA-seq测序方法主要有short- read 的Illumina方法 ； ong-read RNA-seq and direct RNA sequencing

![](image/rna-seq-1-01_H3dMfjLdk7.png)

![](image/rna-seq-1-03-03_DygIw1vZCk.png)

[short-long-rna-seq.pdf](file/short-long-rna-seq_mJ3_IIKh2i.pdf "short-long-rna-seq.pdf")

#### 1.4.1 Short-read VS long-read

![](image/image_Xz7E3LrL2D.png)

> long-read 与Short-read相比更适合在*isoform 检测* & *转录组组装* & *MHC/HLA分型* & *核糖体修饰*等高级分析。

#### 1.4.2 short read sequence

现在NGS测序(short read sequencing)方案主要由以下几家占领市场主导:1. illumina ;2.BGI (华大基因方案)；3.Ion Torrent （现在归属于Thermo Fisher）

![](image/image_05Cemnply1.png)

![](image/image_3WORT39uqG.png)

- BGI的DNBSEQ 测序平台的测序原理与illumina存在本质区别！

  BGI的DNBSEQ测序平台是使用的Phi29聚合酶的环化 → ssCirDNA → 生成DNB (纳米水平) →测序

  ssCirDNA : single-stranded circular DNA (*ssCirDNA*)

  ![](image/image_ojU03ztkUU.png)

  illumina ： 桥式PCR&#x20;

  ![](image/image_-dyezNjEUk.png)

#### 1.4.3 long read sequence

当前的测序 技术除了NGS中的短读长测序，还发展出了以Oxford Nanopore Technologies 公司的Nanopore与PacBio的SMRT测序技术，其可以对mRNA的全长进行测序。

Long- read cDNA sequencing ： ambiguity in the mapping of sequence reads is reduced, and longer transcripts can be identified, which leads to a more complete capture of isoform diversity. Also reduced is the high rate of false-positive splice-junction detection by many short-read RNA-seq computational tools[^9].

> Long- read cDNA sequencing 可以对长转录本进行直接鉴定，其能够较好的解决在short-read cDNA sequencing检测可变剪切中存在假阳性的问题。

![](image/image_jLgOGmX_Dv.png)

**Nanopore 测序技术原理**：纳米孔测序主要是利用电泳的方式将一个未知序列的样品输送穿过一个直径约1纳米孔。这个纳米孔系统会借由施以固定的外加电场在电解液上产生的可检测电流信号，其穿过纳米孔的电流信号强弱则会与纳米孔孔径大小及通过此纳米孔核酸的组成有关。

![](image/image_h9r0HtrweQ.png)

**SMRT 测序技术原理**：SMRT 技術得以實現有賴於 zero-mode waveguide (ZMW) 技術之成熟。ZMW 是一個僅有 20 zeptoliter (10-21 liter) 之大小的孔洞，此空間僅容納數個分子，故可以做到單一 DNA 長鏈定序。透過將 ZMW 表面進行化學修飾後，使得 DNA 聚合酶 (polymerase) 可以被放置於 ZMW 中，當 DNA 聚合酶進行聚合反應時利用光源以毫秒 (millisecond) 快速的進行照射，可以減少螢光訊號損失並可即時 (real-time) 偵測 DNA 聚合時產生的螢光。

#### 1.4.4 Direct RNA-Seq & $m^6A$

![Accurate detection of m 6 A RNA modiﬁcations in native RNA sequences Accurate detection of m 6 A RNA modiﬁcations in native RNA sequences ](image/direct_t_lgq4zDSk.png "Accurate detection of m 6 A RNA modiﬁcations in native RNA sequences Accurate detection of m 6 A RNA modiﬁcations in native RNA sequences ")

Direct RNA-Seq infers the RNA sequence using the current intensity when RNA molecules pass through the pores. Modified nucleotides will emit a different signal intensity compared to unmodified nucleotides, allowing the computational identification of modified sites for each individual RNA molecule using either supervised or comparative approaches.[^10]

> Direct RNA-Seq使用RNA分子通过孔隙时的电流强度来推断RNA序列。与未修饰的核苷酸相比，修饰的核苷酸将发出不同的信号强度。（Direct RNA-Seq 可以对$m^6A$甲基化修饰进行检测）

[Detection of m6A from direct RNA sequencing using a multiple instance learning framework.pdf](<file/Detection of m6A from direct RNA sequencing using .pdf> "Detection of m6A from direct RNA sequencing using a multiple instance learning framework.pdf")

[Accurate detection of m6A RNA modifications in native RNA sequences.pdf](<file/Accurate detection of m6A RNA modifications in nat.pdf> "Accurate detection of m6A RNA modifications in native RNA sequences.pdf")

***

### 1.5 RNA-seq sequencing protocol

The standard workflow begins in the laboratory, with *RNA extraction*, followed by \*mRNA enrichment \*or *ribosomal RNA depletion*, *cDNA synthesis* and *preparation* of an *adaptor-ligated sequencing library*.[^9]

> \*\*RNA-seq \*\*测序主要由 ： 1.*RNA extraction*；2.\*mRNA enrichment \*or *ribosomal RNA depletion*；3.*cDNA synthesis* & *preparation* ；4.*adaptor-ligated sequencing library*；5.\*sequence \*组成。

![Informatics for RNA Sequencing: A Web Resource for Analysis on the Cloud Informatics for RNA Sequencing: A Web Resource for Analysis on the Cloud ](image/Journal.pcbi.1004393.g002_anerJDKSOH.png "Informatics for RNA Sequencing: A Web Resource for Analysis on the Cloud Informatics for RNA Sequencing: A Web Resource for Analysis on the Cloud ")

#### 1.5.1 building library method

使用相关试剂盒组织or 细胞中提取total-RNA后，**直接测序可能会导致rRNA与tRNA的含量爆表**，这就需要采取相关手段将额外的RNA去除从而只保留包含基因表达信息的mRNA序列。现阶段去除额外RNA的方法主要包括以下几种方法。

> \*\*NOTE \*\*: 从细胞或者组织中提取的RNA其中的mRNA的比例很少(mRNA 仅占细胞总 RNA 的 **1-5%**)，大部分的RNA为tRNA和rRNA，如果在建库过程中不将其去除在PCR扩增中获得的大部分序列都是tRNA与rRNA，而这样大比例的tRNA和rRNA对于真正想解释相关基因表达变化则是没有什么意义。
>
> ![](image/Estimate-of-RNA-levels-in-a-typical-mammalian-cell.png)
>
> [ How much RNA does a typical mammalian cell contain? The RNA content and RNA make up of a cell depend very much on its developmental stage and the type of cell https://www.qiagen.com/us/resources/faq?id=06a192c2-e72d-42e8-9b40-3171e1eb4cb8\&lang=en](https://www.qiagen.com/us/resources/faq?id=06a192c2-e72d-42e8-9b40-3171e1eb4cb8\&lang=en " How much RNA does a typical mammalian cell contain? The RNA content and RNA make up of a cell depend very much on its developmental stage and the type of cell https://www.qiagen.com/us/resources/faq?id=06a192c2-e72d-42e8-9b40-3171e1eb4cb8\&lang=en")

[ A survey of best practices for RNA-seq data analysis RNA-sequencing (RNA-seq) has a wide variety of applications, but no single analysis pipeline can be used in all cases. We review all of the major steps in RNA-seq data analysis, including experimental https://www.srcesq.com/articles/10.1186/s13059-016-0881-8](https://www.srcesq.com/articles/10.1186/s13059-016-0881-8 " A survey of best practices for RNA-seq data analysis RNA-sequencing (RNA-seq) has a wide variety of applications, but no single analysis pipeline can be used in all cases. We review all of the major steps in RNA-seq data analysis, including experimental https://www.srcesq.com/articles/10.1186/s13059-016-0881-8")

[ RNAseq建库方法 RNAseq不同建库方法比较。 https://mp.weixin.qq.com/s/DaDa44V45Xaw353wy3mZiA](https://mp.weixin.qq.com/s/DaDa44V45Xaw353wy3mZiA " RNAseq建库方法 RNAseq不同建库方法比较。 https://mp.weixin.qq.com/s/DaDa44V45Xaw353wy3mZiA")

##### **polyA** enrichment

由于**真核生物**mature mRNA序列包含3'-PolyA tail 因此可以使用PolyT序列通过碱基互补来捕获total中的mRNA序列。但是原核生物无法使用该方法😂😂。

![mRNA 的结构：mRNA 由以下部分组成1. 5’cap  ; 2. 5'UTR ; 3. CDS ; 4. 3'UTR ; 5.  3' PolyA tail  mRNA 的结构：mRNA 由以下部分组成1. 5’cap  ; 2. 5'UTR ; 3. CDS ; 4. 3'UTR ; 5.  3' PolyA tail  ](image/image_WQ7OznbvqI.png "mRNA 的结构：mRNA 由以下部分组成1. 5’cap  ; 2. 5'UTR ; 3. CDS ; 4. 3'UTR ; 5.  3' PolyA tail  mRNA 的结构：mRNA 由以下部分组成1. 5’cap  ; 2. 5'UTR ; 3. CDS ; 4. 3'UTR ; 5.  3' PolyA tail  ")

> ***NOTE ***: 现阶段大多数的RNA-seq 都是采用了**polyA 富集** 方法，但是这样的方法会导致**3ʹ端偏好性 \*\*(**这个可以使用Picard软件进行检测**)。同时很多不含 Poly-A 尾巴的非编码 RNA，例如 miRNA 和增强子 RNA 不会被测到。

> \*\*NOTE \*\*:使用ployT富集的方法可能会使得捕获的都是编码RNA序列，其不包含非编码序列！

##### *ribosomal RNA depletion*

在total中rRNA的比例占了大头，因此如果将rRNA干掉就可以确保mature mRNA和一部分非编码RNA保留下来。相关研究表明：**RNase H 方法比 pull-out 方法稳定**

- **pull-out** : 使用特异性或物种特异性探针将rRNA从totalRNA移除；
- **RNAse H** : 使用RNAse H酶将rRNA降解；

##### 1.5.1.3 strand-specific RNA-seq

![https://www.biostars.org/p/70833/ https://www.biostars.org/p/70833/ ](image/image_lMvdsy-JQZ.png "https://www.biostars.org/p/70833/ https://www.biostars.org/p/70833/ ")

链特异性转录组测序（strand-specific RNA-seq）是指转录组测序过程中文库构建采用的链特异性建库方式。此建库方式可以保留转录组测序时转录本的方向信息，即可以确定转录本是来源于基因组上面的正义链还是反义链。

strand-specific RNA-seq 链特异性建库最常用的方法为dUTP建库方法。

> **NOTE:** 在连特异建库的下游分析中相关对比软件与featurecount软件已经提供了相关参数设置

##### 1.5.1.4 small RNA-seq&#x20;

![](image/image_LS7gATmJwu.png)

smallRNA-seq 建库主要是通过使用凝胶进行片段长度筛选后进行建库测序!

[Miran-seq-library-prep.pdf](file/Miran-seq-library-prep_ekmWE-8tE9.pdf " Miran-seq-library-prep.pdf")

[   https://en.wikipedia.org/wiki/Single-molecule\_real-time\_sequencing](https://en.wikipedia.org/wiki/Single-molecule_real-time_sequencing "   https://en.wikipedia.org/wiki/Single-molecule_real-time_sequencing")

> 在翻译组研究中常用的ribo-seq技术就是使用的小RNA-seq建库！：&#x20;

##### **spike-in** (ERCC)

RNA 的 spike-in 一种绝对定量的方法，在原有的 RNAseq 文库中加入已知量的RNA 转录本，目前普遍使用的是 ERCC( The External RNA Control Consortium)。通过在样品制备过程中，混入指定数量的 spike-in，我们就可以知道不同样本中的基因绝对比表达值。

更加详细的解释见 : Normalization & RNA-seq

##### **UMI**

UMI 是单分子识别码（Uniquemolecular identifier）的简称，一般是 10-12bp。UMIs 被认为是一个处理扩增偏好性的方法。在 cDNA 分子扩增前加入随机 UMIs 可以用于识别并计算移除 PCR 引入的重复，而不影响到基因自身表达引入的重复，进而改善基因表达定量的结果和评估等位基因的转录。如果一对测序 reads 包含有相同的 UMI 并且比对到转录组的同样位置，则被认为是技术引入的重复 。

> **主要是用来移除PCR重复**,**该技术在单细胞测序中获得了广泛使用**

### 1.6 Normalization & RNA-seq

Normalization of RNA-seq data has proven essential to ensure accurate inference of expression levels.[^11]Normalization is a crucial step in the analysis of RNA-seq data, having a strong impact on the detection of differentially expressed (DE) genes[^11].

> RNA-seq中对于基因表达的归一化方法对于获得相关基因的表达情况具有重要的影响，采取不同的归一化方法会获得不同的基因表达矩阵。归一化方法也会对下游差异分析获得的差异基因具有很大的影响。

In the last few years, several normalization strategies have been proposed to correct for between-sample distributional differences in read counts, such as differences in ***total counts***, i.e., ***sequencing depths***  and within-sample ***gene-specific effects***, such as ***gene length*** or \*\*\*GC-content \*\*\*effects.

> 现阶段可以使用total counts & 测序深度 & 基因长度 & GC含量对获得的基因表达矩阵进行归一化，但是在复杂的RNA-seq设计中，这些归一化方法可能远远不够。

#### 1.6.1 ERCC

We propose a normalization strategy for RNA-seq, remove unwanted variation (RUV), that uses factor analysis to adjust for nuisance technical effects, based on counts (or residuals counts) for either negative control genes or negative control samples, i.e., genes or samples that are not expected to be influenced by the biological covariates of interest.

> **RUVg**包在RNA-seq实验中添加ERCC实验是基础上，基于阴性对照基因或阴性对照样本的计，使用因子对不希望存在的技术重复进行移除。

The main assumption of RUVg is that one can identify a set of negative control genes. Several types of negative controls could be used, including **housekeeping genes**, **spike-in sequences** (e.g., ERCC), or \*\*“in silico” empirical controls \*\*such as the *Jc* least significantly DE genes based on a first-pass DE analysis performed prior to RUVg normalization.

> RUVg可以使用housekeeping 基因 & ERCC & 或者技术获得的最不显著性基因对矩阵进行归一化。

> 💪🏼**NOTE** : RUVg在做归一化时有一个基本假设为 ：每一个样本中的ERCC含量为一致的。

#### 1.6.2 ERCC & lncRNAs

![](image/image_cYDKBv-Ft3.png)

ERCC (spike-in) can provide estimates for the intracellular abundance of lncRNAs as well as mRNAs in cultured cells.[^12]

ERCC还可以对培养细胞中的lncRNAs & mRNA丰度进行准确估计，与smFISH结果一致。

### 1.7 ERCC & scRNA-seq

**ISnorm** is a package for sc-RNA seq data normalization[^13].

![](image/image_L_JhhkG-7w.png)

[ GitHub - bioliyezhang/ISnorm Contribute to bioliyezhang/ISnorm development by creating an account on GitHub. https://github.com/bioliyezhang/ISnorm](https://github.com/bioliyezhang/ISnorm " GitHub - bioliyezhang/ISnorm Contribute to bioliyezhang/ISnorm development by creating an account on GitHub. https://github.com/bioliyezhang/ISnorm")

[Normalizing single-cell RNA sequencing data with internal spike-in-like genes .pdf](<file/Normalizing single-cell RNA sequencing data with i.pdf> "Normalizing single-cell RNA sequencing data with internal spike-in-like genes .pdf")

***

### 1.8 RNA-seq analysis pipeline

RNA-seq is most often used for analysing differential gene expression (DGE).[^9]

> **DGE** 分析是RNA-seq常用的分析之一！

> RNA-seq 分析工具有很多，主要的分析流程包括一下3种；

In workflow A, aligners such as TopHat, STAR  or HISAT2 use a reference genome to map reads to genomic locations, and then quantification tools, such as HTSeq and featureCounts , assign reads to features. After normalization (usually using methods embedded in the quantification or expression modelling tools, such as trimmed mean of M-values (TMM) ), gene expression is modelled using tools such as edgeR , DESeq2  and limma+voom , and a list of differentially expressed genes or transcripts is generated for further visualization and interpretation.

> **aligners** : TopHat、STAR、HISAT2；

> **quantification** ： HTSeq、featureCounts；

> **normalization** ：TMM  & gene expression ： edgeR、DESeq2、limma+voom&#x20;

In workflow B, newer, alignment-free tools, such as Kallisto and Salmon , assemble a transcriptome and quantify abundance in one step. The output from these tools is usually converted to count estimates (using tximport (TXI)) and run through the same normalization and modelling used in workflow A, to output a list of differentially expressed genes or transcripts.

> **alignment-free tools**(免对比软件也能很快的对转录本进行计数) ： Kallisto 、 Salmon

In workflow C begins by aligning the reads (typically performed with TopHat , although STAR and HISAT  can also be used), followed by the use of CuffLinks  to process raw reads and the CuffDiff2 package to output transcript abundance estimates and a list of differentially expressed genes or transcripts.

> 当要研究的物种没有基因组信息 or 基因组信息不完善，可以通过相关软件进行转录本组装；

> \*\*aligning \*\*： TopHat、STAR、HISAT2

> \*\*Assemble transcripts \*\*: CuffLinks&#x20;

> **DGE** : CuffDiff2

Other tools in common use include StringTie, which assembles a transcriptome model from TopHat  (or similar tools) before the results are passed through to RSEM  or MMSEQ  to estimate transcript abundance, and then to Ballgown to identify differentially expressed genes or transcripts, and SOAPdenovo-trans , which simultaneously aligns and assembles reads for analysis via the path of choice.

> \*\*Assemble transcripts \*\* ：StringTie&#x20;

> **Estimate transcript abundance** ： RSEM、MMSEQ&#x20;

> **Flexible differential expression** : SOAPdenovo-trans

![](image/RNA-SEQ-ANALYSIS_f6431I4Q2M.png)

[RNA-SEQ-ANALYSIS.pdf](file/RNA-SEQ-ANALYSIS_sBZc7JDoaB.pdf "RNA-SEQ-ANALYSIS.pdf")

> \*\*NOTE \*\*: 在对多样本进行分析时，会关注样本之间是否存在批次效应，如果存在除了实验设计之外的批次效应，则需要对获得的基因表达矩阵进行校正 （但是这个校正可能并不是很好的办法，在实验设计阶段可以增加更多的生物学重复！）

#### 1.8.1 Updata Bulk RNA-seq pipeline

![](image/image_oF_kE7UM_H.png)

Bulk RNA Sequencing: A Comparison of the Most Popular Tools and Pipelines[^14]

> Systematic comparison and assessment of RNA-seq procedures for gene expression quantitative analysis
>
> ![](image/image_W9_kyIPT6r.png)
>
> [Systematic comparison and assessment of RNA-seq procedures for gene expression quantitative analysis.pdf](<file/Systematic comparison and assessment of RNA-seq pr.pdf> "Systematic comparison and assessment of RNA-seq procedures for gene expression quantitative analysis.pdf")

#### **Assemble transcripts** de novo&#x20;

![](image/denovo-transcriptions_32t5YjL71g.png)

Taking a similar approach, Guttman et al. use cufflinks called Scripture to reannotate the transcriptomes of three mouse cell lines, defining complete gene models for hundreds of new large intergenic noncoding RNAs (lincRNAs).[^15]

> 当要研究的物种没有基因组信息 or 基因组信息不完善，可以通过相关软件进行转录本组装,这可能会发现一些新的转录本！
>
> [Advancing RNA-Seq analysis.pdf](<file/Advancing RNA-Seq analysis_RSsMkEB3DP.pdf> "Advancing RNA-Seq analysis.pdf")

***

### 1.9 Tumor microenvironment (TME)

The TME often comprises only a small fraction of the tumor and bulk RNA-seq reads; however, the precise identification of small TME cellular subsets, such as natural killer (NK) cells, is essential because they significantly impact therapeutic response and clinical outcome across diverse diseases[^16].&#x20;

> bulk RNA-seq 数据中包含大量的读数，其中部分数据为免疫细胞的数据，因此从RNA-seq中分离出免疫相关要克服数据噪声的影响；常规bulk RNA-seq细胞组成分析是使用scRNA-seq数据集作为训练集进行的解卷积分析，也可以使用非参考数据集（结果更加不靠谱）的解卷积方法。

**bulk-RNA **→ cellular deconvolution(卷积神经网络) (**Cellular deconvolution** ) →** imunce cell rate** → **TME**

[Precise reconstruction of the TME using bulk RNAseq and a machine learning algorithm trained on artificial transcriptomes.pdf](<file/Precise reconstruction of the TME using bulk RNAse.pdf> "Precise reconstruction of the TME using bulk RNAseq and a machine learning algorithm trained on artificial transcriptomes.pdf")

***

### 1.10 scRNA-seq

scRNA-seq & spatial 详细介绍见: [sc-seq](https://www.wolai.com/sqVZZJexu5xADBvMsnRYNu "sc-seq")

***

## 2 Source

[   https://scilifelab.github.io/courses/ngsintro/1905/slides/rnaseq/presentation.html#1](https://scilifelab.github.io/courses/ngsintro/1905/slides/rnaseq/presentation.html#1 "   https://scilifelab.github.io/courses/ngsintro/1905/slides/rnaseq/presentation.html#1")

[ 6 RNAseq data analysis | Master in Bioinformatics and Omic Data Analysis  https://isglobal-brge.github.io/Master\_Bioinformatics/rnaseq-data-analysis.html](https://isglobal-brge.github.io/Master_Bioinformatics/rnaseq-data-analysis.html " 6 RNAseq data analysis | Master in Bioinformatics and Omic Data Analysis  https://isglobal-brge.github.io/Master_Bioinformatics/rnaseq-data-analysis.html")

[   https://combine-australia.github.io/RNAseq-R/06-rnaseq-day1.html#Data\_files\_and\_Resources](https://combine-australia.github.io/RNAseq-R/06-rnaseq-day1.html#Data_files_and_Resources "   https://combine-australia.github.io/RNAseq-R/06-rnaseq-day1.html#Data_files_and_Resources")

***

## 3 Reference

[^1]: 在电脑系统中，快照（英语：snapshot）是整个系统在某个时间点上的状态

[^2]: RNA sequencing: advances, challenges and opportunities

[^3]: Summary of RNA-Seq \[[https://en.wikipedia.org/wiki/RNA-Seq#/media/File:Summary\_of\_RNA-Seq.svg](https://en.wikipedia.org/wiki/RNA-Seq#/media/File:Summary_of_RNA-Seq.svg "https://en.wikipedia.org/wiki/RNA-Seq#/media/File:Summary_of_RNA-Seq.svg")]

[^4]: In silico是指“在硅之中”，也就是说“进行于电脑中，或是经由电脑模拟”之意，此用语是衍生自另外两个在生物学上常用的词组：in vivo（生物活体内）及in vitro（生物活体外）。

[^5]: Next-generation sequencing (NGS) is a technology for determining the sequence of DNA or RNA to study genetic variation associated with diseases or other biological phenomena.

[^6]: Alternative Isoform Regulation in Human Tissue Transcriptomes

[^7]: Landscape of transcription in human cells

[^8]: Enhancers as non-coding RNA transcription units: recent insights and future perspectives

[^9]: RNA sequencing: the teenage years

[^10]: Detection of m6A from direct RNA sequencing using a multiple instance learning framework

[^11]: Normalization of RNA-seq data using factor analysis of control genes or samples

[^12]: Using RNA Sequencing and Spike-in RNAs to Measure Intracellular Abundance of lncRNAs and mRNAs

[^13]: Normalizing single-cell RNA sequencing data with internal spike-in-like genes

[^14]: [https://www.elucidata.io/blog/bulk-rna-sequencing-a-comparison-of-the-most-popular-tools-and-pipelines](https://www.elucidata.io/blog/bulk-rna-sequencing-a-comparison-of-the-most-popular-tools-and-pipelines "https://www.elucidata.io/blog/bulk-rna-sequencing-a-comparison-of-the-most-popular-tools-and-pipelines")

[^15]: Advancing RNA-Seq analysis

[^16]: Precise reconstruction of the TME using bulk RNA-seq and a machine learning algorithm trained on artificial transcriptomes
