# sambamba&#x20;

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 sambamba](#11-sambamba)
- [2 Install](#2-Install)
- [3 tutorial](#3-tutorial)
  - [3.1 view](#31-view)
  - [3.2 sort](#32-sort)
  - [3.3 index](#33-index)
  - [3.4 merge](#34-merge)
  - [3.5 slice](#35-slice)
  - [3.6 flagstat](#36-flagstat)
  - [3.7 markdup](#37-markdup)
- [4 Question:](#4-Question)
- [5 source](#5-source)
- [6 Reference](#6-Reference)

***

***Author***\*\*  : zhang jian\*\*​

***Date***\*\* : 2025-8-9\*\*​

***Version***\*\* : \*\***`1.0v`**

***

> **WARRING** : sambamba 虽然可以加速分析速度，但是在某一些集群和一些服务器硬件下sambamba会报错`Segmentation fault core dumped`

***

## 1 Introduce

### `1.1 sambamba`

**`sambamba`** 是一个自称速度更快滴`mapping` 结果处理软件。支持快速排序、索引、过滤、统计和并行化处理等功能，可用于快速处理大规模NGS数据[^1]。（PS : 但是在实际使用中发现其稳定性不如samtools，特别是在处理如WGS这样超大的bam文件时，往往会由于内核问题导致崩溃。）

![使用单核的 samtools  vs  sambamba 速度对比结果 使用单核的 samtools  vs  sambamba 速度对比结果 ](image/carbon_sf126w2mnZ.svg "使用单核的 samtools  vs  sambamba 速度对比结果 使用单核的 samtools  vs  sambamba 速度对比结果 ")

![使用10核的 samtools  vs  sambamba 速度对比结果 使用10核的 samtools  vs  sambamba 速度对比结果 ](<image/carbon (2)_aStDPeOpQ2.svg> "使用10核的 samtools  vs  sambamba 速度对比结果 使用10核的 samtools  vs  sambamba 速度对比结果 ")

***

## 2 Install

```bash title="install "
# install by conda
mamba install  -c bioconda sambamba -y
# install by brew
brew install brewsci/bio/sambamba
# install by source
wget https://github.com/biod/sambamba/archive/refs/tags/v1.0.1.tar.gz
```


***

## 3 tutorial

### 3.1 view

`sambamba view` 可以有效地**过滤 & 提取** BAM 文件以满足各种条件的比对，以及访问其 SAM 标头和有关参考序列的信息。

```bash title="sambamba view"
sambamba-view [options] <input.bam | input.sam> [region1 [...]]
```


```bash title="sambamba view parameter"
-F  --filter=FILTER      # bam文件的过滤
-f  --format=FORMAT      # 输出文件的格式 sam, bam, json, msgpack
-S  --sam-input          # 指定输入为 SAM 文件
-p  --show-progress      # 显示程序进度
-l, --compression-level  # 输出bam文件的压缩水平 0-9
-o, --output-filename    # 输出文件的名称
-t  --nthreads=NTHREADS  # maximum number of threads to use
-h  --with-header        # print header before reads (always done for BAM output)
-H  --header             # output only header to stdout (if format=bam, the header is printed as SAM)
```


```bash title="sambamba view command"
# extert chr1 mapping result
sambamba view -t 20 xxxx.bam chr1 xxx.chr1.bam
# extert chromosome:start-end range mapping read
sambamba view -f bam input.bam "chromosome:start-end" -o output.bam

```


### 3.2 sort

`sambamba sort` 是可以对bam文件进行排序的命令。

```bash title="sambamba sort command"
sambamba sort -t 10 xxx.bam -o xxx.sort.bam
```


```bash title="sambamba sort parameter"
-m  --memory-limit       # 内存使用限制（xxxGB）
-o  --out=OUTPUTFILE     # 输出文件
-l  --compression-level  # 输出bam文件的压缩水平 0-9
-u  --uncompressed-chunks# 输出未压缩的bam文件，可以提高速度但是I/O消耗可能会增加
-p  --show-progress      # 显示程序进度
-n  --sort-by-name       # 按照read的名称进行排序
-t, --nthreads=NTHREADS

```


### 3.3 index

`sambamba index`可以生成bam & sam & fasta文件的index。

```bash title="sambamba index command"
sambamba index -t 30 JZ23052515-R23019159LD01-Z00655-CQ-T-1_sorted.bam
```


```bash title="sambamba index parameter"
-t/--nthreads=NTHREADS : number of threads to use for decompression
-p/--show-progress     : show progress bar in STDERR
-F/--fasta-input       : specify that input is in FASTA format

```


### 3.4 merge

`sambamba merge`合并多个`bam`文件。

```bash title="sambamba merge command"
sambamba merge OPTIONS <output.bam> <input1.bam> <input2.bam> [...]
```


```bash title="sambamba merge parameter"
-t  --nthreads           # 使用多核心
-l  --compression-level  # 输出bam文件的压缩水平 0-9
-H  --header             # 仅输出合并后的头部信息到标准输出（stdout），并且使用SAM格式
-p  --show-progress      # 显示程序进度
```


### 3.5 slice

`sambamba slice` 是一个快速对bam文件特定区域进行提取的工具，提取区域的语法 `ref:beg-end` ，如果要提取fasta文件需要先建立fasta文件的索引。其也支持STDOUT。

```bash title="sambamba slice parameter"
sambamba-slice [options] <input.bam|input.fasta> [region1 [...]]
# output file name
-o/--output-filename=OUTPUTFILE # output BAM or FASTA filename
-L/--regions=FILENAME  # output only reads overlapping one of regions from the BED file
-F/--fasta-input       # specify that input is in FASTA format

```


### 3.6 flagstat

`sambamba flagstat`可以快速对bam文件中的flag结果进行统计。

```bash title="sambamba flagstat"
sambamba-flagstat [options] <input.bam>
```


```bash title="sambamba flagstat parameter"
-t/--nthreads=NTHREADS : use NTHREADS for decompression
-p/--show-progress     : show progressbar in STDERR
-b/--tabular           : output in csv format
```


```bash title="sambamba flagstat command"
sambamba flagstat input.bam -c input.csv
```


### 3.7 markdup

`sambamba markdup`可以标记or 移除建库过程中由于PCR扩增产生的duplicate reads，默认情况下，标记（mark）重复的读段，或者可以选择移除这些重复的读段，其与Picard工具中使用的标准相同对duplicate reads进行判断。

```bash title="sambamba markdup"
sambamba markdup OPTIONS <input.bam> <output.bam>
```


```bash title="sambamba markdup parameter"
-r, --remove-duplicates : remove duplicates instead of just marking them
-t, --nthreads=NTHREADS : number of threads to use
-l, --compression-level : specify compression level of the resulting file (from 0 to 9)")
-p, --show-progress     : show progressbar in STDERR
```


***

## 4 Question:

\*\*Segmentation fault (core dumped) : \*\*[^2]将`sambamba`相关任务投递到SGE cluster时可能会报错，这可能和内存不足有关；使用`conda`安装的`sambamba`也会遇到该问题，可以尝试使用编译好的`sambamba`版本；

***

## 5 source

> **`sambamba`**\*\* paper :\*\* ​
>
> [Sambamba- fast processing of NGS alignment formats.pdf](<file/Sambamba- fast processing of NGS alignment formats.pdf> "Sambamba- fast processing of NGS alignment formats.pdf")

***

## 6 Reference

[^1]: [https://github.com/biod/sambamba](https://github.com/biod/sambamba "https://github.com/biod/sambamba")

[^2]: [https://github.com/biod/sambamba/issues/186](https://github.com/biod/sambamba/issues/186 "https://github.com/biod/sambamba/issues/186")
