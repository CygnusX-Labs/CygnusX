# bamCompare

## 目录

- [1 bamCompare](#1-bamCompare)
  - [1.1 algorithm ](#11-algorithm-)
  - [1.2 bamCompare parameter](#12-bamCompare-parameter)

### `1 bamCompare`

**`bamCompare`** 可以用来生成 基于两个相互比较的 BAM 文件生成的bigWig 或 bedGraph 文件，同时在生成过程中会对这些文件进行测序深度的标准化处理。

#### 1.1 algorithm&#x20;

`bamCompare`算法的工作原理，它分为两个主要步骤：

1. 每个样本的缩放/深度标准化：&#x20;
   1. **使用缩放（使用SES或读数计数方法）标准化** ：则会确定适当的缩放因子，以考虑测序深度的差异。SES代表“缩放因子估计”，这是一种用于校正不同样本之间测序深度差异的方法。读数计数方法则基于每个样本的总读数来计算缩放因子。
   2. **使用RPKM（每千个碱基每百万映射读数）、BPM（每百万映射读数的bin数）或CPM（每百万映射读数的计数）方法对单个样本进行标准化**。如果没有指定任何标准化方法，则不进行标准化处理。
2. **缩放/标准后计算bin的比率、比率、差异**： 在考虑了缩放之后，算法会对基因组进行遍历，并计算每个固定宽度的bin的log2比率、比率、差异等。

#### `1.2 bamCompare` parameter

```bash title="bamCompare parameter"
# Required arguments
--bamfile1, -b1 : 排序后的BAM文件1。通常是处理组的BAM文件。
--bamfile2, -b2 : 排序后的BAM文件2。通常是对照组的BAM文件。
# Output arguments
--outFileName, -o    : 输出文件名。
--outFileFormat, -of : 输出文件格式 bigwig, bedgraph
# Optional arguments
--scaleFactorsMethod : 缩放样本的方法 readCount, SES, None
                       可以设置为None，并使用——normalizeUsing <method>中的选项
--sampleLength, -l   : 仅在SES被选为scaleFactorsMethod时相关。
                       为了计算SES，指定将随机抽样以计算缩放因子的区域的长度（以碱基为单位）（参见——numberOfSamples）。
                       如果你的样本没有很好的测序深度，考虑增加抽样区域的大小，
                       以最小化使用零覆盖区域的可能性。（默认：1000）
--numberOfSamples, -n :  仅在SES被选为scaleFactorsMethod时相关。
                         从基因组中取样的数量，用于计算缩放因子。（默认：100000.0）
--scaleFactors  : 手动设置此参数以避免计算scaleFactors。
                  格式是scaleFactor1:scaleFactor2。
                  例如，scaleFactor 0.7:1将导致第一个BAM文件乘以0.7，
                  而第二个BAM文件不进行缩放（乘以1）。
--operation   : 输出两个样本对比值的计算方法默认情况下为log2
                log2, ratio, subtract, add, mean, reciprocal_ratio, first, second
--pseudocount : 为了避免x/0，使用一个小数。仅在使用——operation log2或——operation ratio时有用。
                你可以通过提供两个值（第一个值用作分子伪计数，第二个用作分母伪计数）来指定不同的值作为伪计数。（默认：[1]）
--skipZeroOverZero : 跳过两个BAM文件都缺乏覆盖的bin。这是在添加任何适用的伪计数之前确定的。
--binSize, -bs     : 输出的bigwig/bedgraph文件的bin大小，以碱基为单位。（默认：50）
--region, -r       : 限制操作的基因组区域——这在测试参数以减少计算时间时很有用。
                     格式是chr:start:end，例如——region chr10或——region chr10:456700:891000。
--blackListFileName, -bl : 包含应该从所有分析中排除的区域的BED或GTF文件。
--numberOfProcessors, -p : 要使用的处理器数量。
--verbose, -v            : 设置以查看处理消息。
```


> **NOTE** : `bamCompare`对两个bam文件进行对比时可以使用不同的缩放/标准化方法对数据进行处理，如果不使用**缩放（使用SES或读数计数方法）**可以使用**RPKM/BPM/CPM**对数据进行标准化。

```bash title="Read coverage normalization options"
--effectiveGenomeSize : 有效基因组大小是指可映射基因组的部分。
--normalizeUsing      : 归一化方法RPKM, CPM, BPM, RPGC, None
                        使用输入的方法之一来归一化每个bin的读取数。默认情况下，不执行归一化。
                        RPKM = 每千碱基每百万映射读取数；
                        CPM = 每百万映射读取数的计数，与RNA-seq中的CPM相同；
                        BPM = 每百万映射读取数的bin，与RNA-seq中的TPM相同；
                        RPGC = 每基因组内容的读取数（1x归一化）；
--exactScaling        : 对所有的数据进行处理，以确定用于输出的确切Scaling数值。
--ignoreForNormalization, -ignore  : 一个由空格分隔的染色体名称列表，包含那些应该被排除在归一化计算之外的染色体。
--skipNonCoveredRegions, --skipNAs : 此参数决定是否跳过BAM文件中未被读取覆盖的区域。
--smoothLength        : 平滑长度定义了一个窗口，大于binSize，以平均读取数。
```


```bash title="Read processing options"
# Read processing options
--extendReads/-e    ：延长 reads 的长度，对应 RNA-seq 数据不适合
--ignoreDuplicates  ：忽略重复的 reads
--minMappingQuality ：reads 最小比对质量值，整数型
--centerReads       ：中心化 reads，可获得更陡峭的峰
--samFlagInclude    ：根据 sam 格式的 flag 来保留对应的 reads 用于分析
--samFlagExclude    ：根据 sam 格式的 flag 来剔除对应的 reads 用于分析
--minFragmentLength ：reads 的 Fragment 最小长度，对应于 ATAC-seq 数据可用来筛选单核小体和多核小体
--maxFragmentLength ：reads 的 Fragment 最大长度

```


\*\*bamCompare RPKM Compare : \*\*

```bash title="bamCompare"
bamCompare -b1  1_sorted.bam \
           -b2  2_sorted.bam \
           --outFileName RNA-seq_test.RPKM.bw \
           --outFileFormat bigwig \
           -p 30 \
           --verbose \
           -bs 10 \
           --scaleFactorsMethod None \
           --normalizeUsing RPKM \
           --smoothLength 12 \
           --minMappingQuality 30
```


\*\*bamCompare RPKM Compare \*\***bedgraph** \*\*: \*\*

```bash 
bamCompare -b1  JZ24050910-SQ24015264-SQ24015264_sorted.bam \
           -b2  JZ24050911-SQ24015265-SQ24015265_sorted.bam \
           --outFileName RNA-seq_test.RPKM.bedgraph \
           --outFileFormat bedgraph \
           -p 70 \
           --verbose \
           -bs 10 \
           --scaleFactorsMethod None \
           --normalizeUsing RPKM \
           --smoothLength 12 \
           --minMappingQuality 30
```


```bash title="RNA-seq_test.RPKM.bedgraph "
chr1    0       10000   0
chr1    10000   10040   -1.64353
chr1    10040   10110   -2.39193
chr1    10110   10150   -1.64353
chr1    10150   10540   0
chr1    10540   10620   -2.39193
chr1    10620   14400   0
chr1    14400   14460   1.60417
chr1    14460   14470   2.832
chr1    14470   14480   3.19547
chr1    14480   14490   1.55194
chr1    14490   14510   0.803543
chr1    14510   14520   1.05147
chr1    14520   14530   0.575778
```
