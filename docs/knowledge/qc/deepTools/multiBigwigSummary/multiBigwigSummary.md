# multiBigwigSummary

## 目录

- [1 multiBigwigSummary](#1-multiBigwigSummary)
  - [1.1 multiBigwigSummary subcommand](#11-multiBigwigSummary-subcommand)
  - [1.2 command](#12-command)
    - [1.2.1 bins](#121-bins)
  - [1.3 BED-file](#13-BED-file)

### `1 multiBigwigSummary`

bw → `multiBigwigSummary` → .npz → `plotCorrelation` | `plotPCA`

`multiBigwigSummary` ：计算两个或更多的`bigWig`文件每个文件在每个基因组区域的平均分数。通过在`bin`模式下运行程序，可以对整个基因组进行这种分析，或者在`BED`文件模式下对用户选定的特定区域进行分析。最常见的是，`multiBigwigSummary`的默认输出（一个压缩的numpy数组，.npz）被其他工具如`plotCorrelation`或`plotPCA`用于可视化和诊断目的。**(ps:****`multiBigwigSummary`****和****`multiBamSummary`**** 命令具有相同的作用，只是起始文件存在一定区别）**

#### `1.1 multiBigwigSummary` subcommand

`bins` ：平均分数是基于等大小的区间（默认为10千碱基）计算的，这些区间连续覆盖整个基因组。唯一的例外是染色体的最后一个区间，它通常更小。这种模式的输出通常用于评估不同bigWig文件之间的整体相似性。

`BED-file` : 用户提供一个BED文件，其中包含了应该考虑进行分析的所有区域。一个常见的用途是比较多组样本在一组预定义的峰值区域上的分数（例如ChIP-seq分数）。

#### 1.2 command

##### `1.2.1 bins`

```bash title="bins parameter"
# Required arguments
--bwfiles, -b           : 用空格分隔的bigWig文件列表。
--outFileName, -out, -o : 用于保存压缩矩阵文件（npz格式）的文件名，该文件是“plotPCA”和“plotCorrelation”工具所需的。
# Optional arguments
--labels, -l   : 用户定义的标签，而不是从文件名中的默认标签。多个标签必须用空格分隔，
                 例如，--labels sample1 sample2 sample3
--smartLabels  : 而不是手动指定输入bigWig文件的标签，这会导致deepTools在移除路径和
                 扩展名后使用文件名。
--chromosomesToSkip : 你不想包括在内的染色体列表。有助于移除“随机”或“额外”的染色体。
--binSize, -bs      : 从基因组中采样的窗口大小（以碱基为单位）。（默认：10000）
--distanceBetweenBins, -n : 默认情况下，multiBigwigSummary考虑相邻的指定
                            --binSize的区间。然而，为了减少计算时间，可以给出更大的区间距离。
                            更大的距离会导致考虑的区间更少。（默认：0）
--region, -r             : 限制操作的基因组区域 - 这在测试参数以减少计算时间时很有用。
                           格式是chr:start:end，例如 --region chr10 或 
                           --region chr10:456700:891000。
--blackListFileName, -bl : 包含应该从所有分析中排除的区域的BED或GTF文件。
                           目前，这是通过拒绝与条目重叠的基因组块来工作的。
                           因此，对于BAM文件，如果一个读取部分重叠了一个
                           黑名单区域或者一个片段跨越了它，那么读取/片段
                           可能仍然会被考虑。请注意，如果相关，你应该调整有效的基因组大小。
--numberOfProcessors, -p : 要使用的处理器数量。输入“max/2”使用最大处理器数量的一半，
                           或者输入“max”使用所有可用的处理器。（默认：1）
--verbose, -v  : 设置为查看处理消息。
# Output optional options
--outRawCounts : 将每个bigWig文件的每个区域的平均分数保存到一个单独的制表符分隔文件中。
# Other
--version : 显示程序的版本号并退出

```


```bash title="multiBigwigSummary bins example"
multiBigwigSummary bins -b 15-IgG.bw 15-f4-1.bw 15-f4-2.bw 15-sh-IgG.bw 15-sh-f4-1.bw 15-sh-f4-2.bw  \
                        -p 30 \
                        --outRawCounts 15_bins.multiBigwigSummary.tsv \
                        -o  15_bins.multiBigwigSummary.npz \
                        -v
```


```bash title="15_bins.multiBigwigSummary.tsv"
#'chr'  'start' 'end'   '15-IgG.bw'     '15-f4-1.bw'    '15-f4-2.bw'    '15-sh-IgG.bw'  '15-sh-f4-1.bw' '15-sh-f4-2.bw'
chr2    102940000       102950000       0.0     0.0     0.0     0.0     0.0     0.1035027015209198
chr2    102950000       102960000       0.0     0.0     0.0     0.0     0.13301660418510436     0.42551140069961546
chr2    102960000       102970000       0.0     0.020976439714431763    0.0     0.8024939727783204      0.09549905180931091     0.04600120067596
chr2    102970000       102980000       0.0     0.01573230028152466     0.0     0.43134020805358886     0.04774959921836853     0.09200240135192
chr2    102980000       102990000       0.0     0.0     0.0     0.0     0.006821349859237671    0.2932579723000526
```


#### `1.3 BED-file`

`BED-file`可以对特定分析区域（BED文件）的覆盖率进行计算。一个常见的用途是比较不同样本在一组预定义的峰值区域上的分数（例如ChIP-seq分数）。

```bash title="BED-file parameter"
# Required arguments
--bwfiles, -b           : 用空格分隔的bigWig文件列表。
--outFileName, -out, -o : 用于保存压缩矩阵文件（npz格式）的文件名，该文件是“plotPCA”和“plotCorrelation”工具所需的。
--BED                   : 将分析限制在该文件中指定的区域。
# Optional arguments
--labels, -l : 用户定义的标签，而不是从文件名中的默认标签。
               多个标签必须用空格分隔，例如，--labels sample1 sample2 sample3
--smartLabels : 而不是手动指定输入bigWig文件的标签，
                这会导致deepTools在移除路径和扩展名后使用文件名。
--chromosomesToSkip : 你不想包括在内的染色体列表。有助于移除“随机”或“额外”的染色体。
--region, -r             : 限制操作的基因组区域 - 这在测试参数以减少计算时间时很有用。
                           格式是chr:start:end，例如 --region chr10 或 
                           --region chr10:456700:891000。
--blackListFileName, -bl : 包含应该从所有分析中排除的区域的BED或GTF文件。
                           目前，这是通过拒绝与条目重叠的基因组块来工作的。
                           因此，对于BAM文件，如果一个读取部分重叠了一个
                           黑名单区域或者一个片段跨越了它，那么读取/片段
                           可能仍然会被考虑。请注意，如果相关，你应该调整有效的基因组大小。
--numberOfProcessors, -p : 要使用的处理器数量。输入“max/2”使用最大处理器数量的一半，
                           或者输入“max”使用所有可用的处理器。（默认：1）
--verbose, -v  : 设置为查看处理消息。
# Output optional options
--outRawCounts : 将每个bigWig文件的每个区域的平均分数保存到一个单独的制表符分隔文件中。
# Other
--version : 显示程序的版本号并退出

```


```bash title="multiBigwigSummary BED-file example"
multiBigwigSummary BED-file -b 15-IgG.bw 15-f4-1.bw 15-f4-2.bw 15-sh-IgG.bw 15-sh-f4-1.bw 15-sh-f4-2.bw  \
                        -p 30 \
                        --BED /glusterfs/home/local_liu_yang/01.database/deeptools_database/hg38_gencode_v39/hg38_V39_gencode.bed \
                        --outRawCounts 15_bed.multiBigwigSummary.tsv \
                        -o  15_bed.multiBigwigSummary.npz \
                        -v
```
