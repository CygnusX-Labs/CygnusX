# plotEnrichment

## 目录

- [1 plotEnrichment](#1-plotEnrichment)
- [2 plotEnrichment parameter](#2-plotEnrichment-parameter)

### `1 plotEnrichment`

`plotEnrichment`可以对特定BED/GTF文件中的特定区域的信号富集情况进行计算与绘图。这个工具还可以输出底层的数据点。绘制的指标是总读数的一个分数。在BED文件中的区域被分配到“峰值”特征上。

### `2 plotEnrichment` parameter

```bash 
# Required arguments
--bamfiles, -b : 用空格分隔的索引化BAM文件列表。
--BED          : 将富集分析限制在这些BED/GTF文件指定的区域。
# Optional arguments
--plotFile, -o : 保存图表的文件。
--attributeKey : 不是从GTF文件的特征列中派生标签，而是使用给定的属性键，例如gene_biotype。
--labels, -l   : 用户定义的标签，而不是从文件名中的默认标签。
--smartLabels  : 自动设置标签
--regionLabels : 对于BED文件，给其区域的标签是文件名，但可以通过提供自定义标签来覆盖。
--plotTitle,-T : 图表的标题，将打印在生成的图像顶部。
--plotFileFormat : 可能的选择：png, pdf, svg, eps, plotly
--outRawCounts : 将每个区域的计数保存到制表符分隔的文件中。
--perSample    : 按样本分组绘制图表，而不是按特征类型（默认）。
--variableScales : 默认情况下，y轴始终是0-100。这允许限制轴的范围。
--plotHeight   : 图表高度，以厘米为单位。（默认：20）
--plotWidth    : 图表宽度，以厘米为单位。最小值为1厘米。（默认：20）
--colors       : 用于绘制线条的颜色列表。接受颜色名称和html十六进制字符串（例如，#eeff22）
- `--numPlotsPerRow`：每行图表的数量。（默认：4）

- `--alpha`：用于条形图的alpha通道（透明度）。默认为0.9，值必须在0和1之间。

- `--Offset`：使用这个偏移量作为每个读取内的信号。这在RiboSeq或GROseq等情况下很有用，信号可能在读取开始的12、15或0个碱基之后。这可以与 `--FilterRNAstrand` 选项配对使用。注意，负值表示从每个读取的末端偏移。值为1表示对齐的（考虑对齐方向）第一个碱基。同样，-1是最后一个碱基的对齐。不允许偏移量为0。如果指定了两个值，则将用于指定位置范围。注意，指定 `--Offset 5 -1` 将使用第5个到最后一个位置，这等同于从5'端修剪4个碱基。

- `--version`：显示程序的版本号并退出。

- `--region, -r`：限制操作的基因组区域 - 这在测试参数以减少计算时间时很有用。格式是chr:start:end，例如 `--region chr10` 或 `--region chr10:456700:891000`。

- `--blackListFileName, -bl`：包含应该从所有分析中排除的区域的BED或GTF文件。目前，这通过拒绝与条目重叠的基因组块来工作。因此，对于BAM文件，如果读取部分与黑名单区域重叠或片段跨越它，则读取/片段仍可能被考虑。请注意，如果相关，您应该调整有效的基因组大小。

- `--numberOfProcessors, -p`：要使用的处理器数量。输入“max/2”使用最大处理器数量的一半，或“max”使用所有可用处理器。（默认：1）

- `--verbose, -v`：设置为查看处理消息。

**BED12参数：**
- `--keepExons`：对于BED12文件，使用每个外显子作为区域，而不是第2/3列。

**读取处理选项：**
- `--extendReads, -e`：此参数允许将读取扩展到片段大小。如果设置，每个读取都会扩展，无一例外。注意：这种特性通常**不推荐**用于剪接读取数据，如RNA-seq，因为它会将读取扩展到跳过的区域。单端：需要用户提供最终片段长度的值。超过此片段长度的读取不会被扩展。配对端：有配对的读取总是扩展以匹配两个读取配对定义的片段大小。未配对的读取，配对读取映射得太远（>4倍片段长度）或甚至映射到不同染色体的读取像单端读取一样处理。输入片段长度值是可选的。如果没有指定值，则从数据中估计（所有配对读取的片段大小的平均值）。

- `--ignoreDuplicates`：如果设置，具有相同方向和起始位置的读取只会被考虑一次。如果读取是配对的，配对的位置也必须一致才能忽略读取。

- `--minMappingQuality`：如果设置，只有映射质量分数至少为这个值的读取才会被考虑。

- `--centerReads`：通过添加此选项，读取将根据片段长度居中。对于配对端数据，读取在由两个片段端定义的片段长度处居中。对于单端数据，使用给定的片段长度。这个选项很有用，可以在富集区域周围获得更清晰的信号。

- `--samFlagInclude`：根据SAM标志包括读取。例如，要获得只有第一配对的读取，使用标志64。这很有用，因为否则第二配对也会被考虑用于覆盖。（默认：无）

- `--samFlagExclude`：根据SAM标志排除读取。例如，要获得只映射到正链的读取，使用 `--samFlagExclude 16`，其中16是映射到负链的读取的SAM标志。（默认：无）

- `--minFragmentLength`：读取/配对包含所需的最小片段长度。这个选项主要用于ATACseq实验，用于过滤单核或双核小体片段。（默认：0）

- `--maxFragmentLength`：读取/配对包含所需的最大片段长度。（默认：0）

**示例用法：**
`plotEnrichment -b file1.bam file2.bam –BED peaks.bed -o enrichment.png`

```
