# multiBamSummary

## 目录

- [1 multiBamSummary](#1-multiBamSummary)
- [2 multiBamSummary subcommands](#2-multiBamSummary-subcommands)
- [3 Parameter](#3-Parameter)
  - [3.1 bin](#31-bin)
  - [3.2 BED-file](#32-BED-file)

#### 1 multiBamSummary

`multiBamSummary` 可以对两个或更多 BAM 文件的基因组区域的读覆盖度进行计算，并且`deeptools`也提供了`plotCorrelation` & `plotPCA`进行绘图可视。`multiBamSummary` 的标准输出是一个压缩的 numpy 数组（.npz）它可以直接用于使用工具`plotCorrelation`计算和可视化读覆盖度之间的成对相关性值。同样，`plotPCA` 可用于使用 .npz 文件进行读覆盖度的主成分分析。请注意，如果只想生成 `bedGraph` 文件（即，使用 `--outRawCounts` 选项；如果仅提供了单个文件，则默认输出文件不能被任何 `deepTools` 程序使用！），则只推荐使用单个 `bigWig` 文件。

bam  →  `multiBamSummary` → .npz → `plotPCA` & `plotCorrelation`

#### 2 multiBamSummary subcommands

> `multiBamSummary` 共提供了两种分析模式`bins` & `BED-file`：`bins`可以对整个基因组进行分析 & `BED-file`计算特定区域的读覆盖度
>
> 1. `bins` ：覆盖度计算是针对等大小的连续区间（默认为10kb）进行的。这种模式有助于评估BAM文件在全基因组范围内的相似性。区间大小和区间之间的距离可以调整。
> 2. `BED-file` : 用户提供一个BED文件，该文件包含所有应该被考虑进行覆盖度分析的区域。一个常见的用途是对于一组峰值区域，比较两个不同样本之间的ChIP-seq覆盖度。

#### 3 Parameter

##### `3.1 bin`

`bins` ：覆盖度计算是针对等大小的连续区间（默认为10kb）进行的。这种模式有助于评估BAM文件在全基因组范围内的相似性。区间大小和区间之间的距离可以调整。

```bash title="Parameter"
# Required arguments
--bamfiles, -b          : 列出由空格分隔的已索引的BAM文件
--outFileName, -out, -o : 用于保存覆盖率矩阵的文件名。这个矩阵随后可以使用plotCorrelation或者plotPCA进行绘制
# Optional arguments
--labels, -l   :  用户定义的标签代替了文件名中的默认标签。多个标签需要用空格分隔，例如：-labels sample1 sample2 sample3
--smartLabels  :  deepTools这个工具会自动使用文件名
--genomeChunkSize : 手动指定提供给每个处理器的基因组大小。默认值“None”表示这将由BAM文件的读取密度决定
--binSize, -bs    :  窗口用于采样基因组的长度（碱基对）。（默认值：10000）
--distanceBetweenBins, -n : 默认情况下，multiBamSummary会考虑指定的——binSize的连续bin。然而，为了减少计算时间，可以设置更大的bin间隔。更大的间隔会导致考虑的bin数量减少。（默认值：0）
--region, -r      : 仅对特定基因组区域进行分析
--blackListFileName, -bl : 一个BED或GTF文件，其中包含了应该从所有分析中排除的区域
--numberOfProcessors, -p : 分析使用的线程数
# Output optional options
--outRawCounts   : 将每个区域的计数保存到一个制表符分隔的文件中
--scalingFactors : 计算缩放因子（按照DESeq2的方式），使其与bamCoverage兼容，并将它们写入文件。该文件包含制表符分隔的“样本”和“缩放因子”两列。
# Read processing options
--extendReads, -e   : 允许将读取扩展到片段大小
--ignoreDuplicates  : 如果设置，具有相同方向和起始位置的读取将只被考虑一次。如果读取是成对的，那么配对的位置也必须相同才能忽略一个读取。
--minMappingQuality : 只保留那些映射质量得分至少达到这个阈值的读取（reads）
--centerReads       ：中心化 reads，可获得更陡峭的峰
--samFlagInclude    ：根据 sam 格式的 flag 来保留对应的 reads 用于分析
--samFlagExclude    ：根据 sam 格式的 flag 来剔除对应的 reads 用于分析
--minFragmentLength ：reads 的 Fragment 最小长度，对应于 ATAC-seq 数据可用来筛选单核小体和多核小体
--maxFragmentLength ：reads 的 Fragment 最大长度

```


```bash title="multiBamSummary bins example"
multiBamSummary bins \
 --bamfiles AFT1_0h_merge.bam AFT1_4h_merge.bam \
 --minMappingQuality 30 \
 --labels AFT1_0h AFT1_4h \
 -p 4 \
 -out readCounts.npz --outRawCounts readCounts.tab
```


##### `3.2 BED-file`

`BED-file` : 用户提供一个BED文件，该文件包含所有应该被考虑进行覆盖度分析的区域。一个常见的用途是对于一组峰值区域，比较两个不同样本之间的ChIP-seq覆盖度。

```bash title="Parameter"
# Required arguments
--bamfiles, -b          : 列出由空格分隔的已索引的BAM文件
--outFileName, -out, -o : 用于保存覆盖率矩阵的文件名。这个矩阵随后可以使用plotCorrelation或者plotPCA进行绘制
--BED                   : 将覆盖范围分析限制在这些文件中指定的区域
# Optional arguments
--labels, -l   :  用户定义的标签代替了文件名中的默认标签。多个标签需要用空格分隔，例如：-labels sample1 sample2 sample3
--smartLabels  :  deepTools这个工具会自动使用文件名
--genomeChunkSize : 手动指定提供给每个处理器的基因组大小。默认值“None”表示这将由BAM文件的读取密度决定
--binSize, -bs    :  窗口用于采样基因组的长度（碱基对）。（默认值：10000）
--distanceBetweenBins, -n : 默认情况下，multiBamSummary会考虑指定的——binSize的连续bin。然而，为了减少计算时间，可以设置更大的bin间隔。更大的间隔会导致考虑的bin数量减少。（默认值：0）
--region, -r      : 仅对特定基因组区域进行分析
--blackListFileName, -bl : 一个BED或GTF文件，其中包含了应该从所有分析中排除的区域
--numberOfProcessors, -p : 分析使用的线程数
# Output optional options
--outRawCounts   : 将每个区域的计数保存到一个制表符分隔的文件中
--scalingFactors : 计算缩放因子（DESeq2方式），适用于与bamCoverage一起使用，并将它们写入文件。该文件有以制表符分隔的“样本”和“缩放因子”两列
--extendReads, -e   : 允许将读取扩展到片段大小
--ignoreDuplicates  : 如果设置，具有相同方向和起始位置的读取将只被考虑一次。如果读取是成对的，那么配对的位置也必须相同才能忽略一个读取。
--minMappingQuality : 只保留那些映射质量得分至少达到这个阈值的读取（reads）
--centerReads       ：中心化 reads，可获得更陡峭的峰
--samFlagInclude    ：根据 sam 格式的 flag 来保留对应的 reads 用于分析
--samFlagExclude    ：根据 sam 格式的 flag 来剔除对应的 reads 用于分析
--minFragmentLength ：reads 的 Fragment 最小长度，对应于 ATAC-seq 数据可用来筛选单核小体和多核小体
--maxFragmentLength ：reads 的 Fragment 最大长度
# D.GTF/BED12 
--metagene : 当提供 bed12 或 gtf 格式的区间文件时，会合并外显子后再进行计算，
             而不是基于含有内含子区域计算，如果提供 bed3 或 bed6 格式的，则
             第 2 列和第 3 列作为一个外显子
--transcriptID : 当区间为 gtf 格式时，使用 transcripts 作为特征来计算
--exonID       : 当区间为 gtf 格式时，使用 exons 作为特征来计算
--transcript_id_designator : 设置特征的选择，默认 transcript_id
# Other
--version
```


```bash title="multiBamSummary BED-file example"
# multiBamSummary BED-file example
multiBamSummary BED-file -b ./*bam \
                         --BED gene.bed  \
                         --binSize 50000 \
                         --minMappingQuality 30 \
                         -p 70 \
                         -out BED_readCounts.npz --outRawCounts BED_readCounts.tab

```


[BED\_readCounts.npz](file/BED_readCounts_kjv5ZeyE6Q.npz "BED_readCounts.npz")

[BED\_readCounts.tab](file/BED_readCounts_jLoDCiCU81.tab "BED_readCounts.tab")
