# bigwigCompare

## 目录

- [1 bigwigCompare](#1-bigwigCompare)
- [2 bigwigCompare parameter](#2-bigwigCompare-parameter)
  - [2.1 operation](#21-operation)
- [3 bigwigCompare example](#3-bigwigCompare-example)
  - [3.1 subtract](#31-subtract)

#### `1 bigwigCompare`

`bigwigCompare`可以对bam转换后获得的bigWig进行对比。基因组被划分成等大小的bin，然后计算每个BAM文件中每个bin发现的读取数量，最后报告一个汇总值。这个值可以是每个bin读取数量的比率、比率的log2、总和或差异。

#### `2 bigwigCompare` parameter

```bash title="bigwigCompare parameter"
# Named Arguments
--bigwig1, -b1 : 第一个Bigwig文件。通常是处理组的文件。
--bigwig2, -b2 : 第二个Bigwig文件。通常是对照组的文件。
--scaleFactors : 设置此参数以乘以一个常数来缩放bigwig值。
                 格式是scaleFactor1:scaleFactor2。
                 例如，0.7:1表示将第一个bigwig文件的值乘以0.7，
                 而第二个bigwig文件的值不缩放。
--pseudocount  : 一个小数，用于避免除以零的情况。
                 仅在与“--operation log2”或“--operation ratio”一起使用时有用。
                 你可以通过提供两个值（第一个值用作分子的伪计数，第二个用作分母的伪计数）
                 来为分子和分母指定不同的伪计数值。（默认值：1）
--skipZeroOverZero : 跳过两个BAM文件都缺乏覆盖的区域。
                     这是在添加任何适用的伪计数之前确定的。
--operation    : 可能的选择：log2, ratio, subtract, add, 
                 mean, reciprocal_ratio, first, second（默认：“log2”）
--skipNonCoveredRegions, --skipNAs : 此参数决定是否跳过bigWig文件中未覆盖的区域（没有分数的区域）。
--fixedStep    : 输出所有大小为--binSize的bin，而不是合并具有相等值的邻近bin。
--binSize, -bs : 输出bigwig/bedgraph文件的bin大小，以碱基为单位。（默认：50）
--region, -r   : 限制操作的基因组区域
--blackListFileName, -bl  : 包含应该从所有分析中排除的区域的BED或GTF文件。
--numberOfProcessors, -p  : 要使用的处理器数量。
# Named Arguments
--outFileName, -o     : 输出文件名。
--outFileFormat, -of  : 输出文件类型：bigwig, bedgraph

```


##### 2.1 operation

> `bigwigCompare` 的 `--operation` 参数可以对两个样本进行以下处理：
>
> - **`log2`** : 计算两个 bigWig 文件信号的 log2 比值。输出为 log2(第一个样本的信号 / 第二个样本的信号)。
> - **`ratio`** : 计算两个 bigWig 文件中信号的比值。输出为第一个样本的信号除以第二个样本的信号。
> - **`subtract`** : 将第一个 bigWig 文件中的信号减去第二个文件中的信号。输出为第一个样本的信号减去第二个样本的信号。
> - **`add`** : 将两个 bigWig 文件中的信号相加。输出为两个文件中信号的和。
> - **`mean`** : 计算两个 bigWig 文件中信号的均值。输出为两个文件中信号的平均值。
> - **`reciprocal_ratio`** : 计算两个 bigWig 文件信号的倒数比值。即输出为 (第二个样本的信号 / 第一个样本的信号)。
> - **`first`** ： 仅输出第一个 bigWig 文件的信号，忽略第二个 bigWig 文件。这个操作一般用于比较分析时需要只显示第一个样本的情况。
> - **`second`** : 仅输出第二个 bigWig 文件的信号，忽略第一个 bigWig 文件。这种情况与 `first` 类似，只是用于展示第二个样本的信号。

#### `3 bigwigCompare` example

```bash title="bigwigCompare example"
bigwigCompare -b1 xxx.bw -b2 xxx.bw \
              --operation log2 \
              -p 20 \
              -of bedgraph \
              -o bigwigCompare.bedgraph
```


##### `3.1 subtract`[^1]

> NOTE : bigwigCompare的`subtract`函数可以做两个bw相减的操作
>
> ```bash title="bigwigCompare subtract"
> # 293-sh-f4-2.bw 减去 293-sh-IgG.bw
> bigwigCompare \
>     -b1 293-sh-f4-2.bw \
>     -b2 293-sh-IgG.bw \
>     --operation subtract \
>     -p 20 \
>     -o 293-sh-f4-2-subtract.bw
> ```
>

[^1]: [https://www.jieandze1314.com/post/cnposts/242/](https://www.jieandze1314.com/post/cnposts/242/ "https://www.jieandze1314.com/post/cnposts/242/")
