# Seqtk

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 Seqtk](#11-Seqtk)
- [2 Install](#2-Install)
  - [2.1 install by source](#21-install-by-source)
  - [2.2 install by conda](#22-install-by-conda)
- [3 Tutorial](#3-Tutorial)
  - [3.1 fastq → fasta](#31-fastq--fasta)
  - [3.2 FASTQ Size](#32-FASTQ-Size)
  - [3.3 FASTA comp](#33-FASTA-comp)
  - [3.4 Downsample](#34-Downsample)
  - [3.5 subseq](#35-subseq)
  - [3.6 fqchk](#36-fqchk)
  - [3.7 mergepe](#37-mergepe)
  - [3.8 split](#38-split)
  - [3.9 trimfq ](#39-trimfq-)
  - [3.10 hety ](#310-hety-)
  - [3.11 gc](#311-gc)
  - [3.12 mutfa](#312-mutfa)
  - [3.13 mergefa](#313-mergefa)
  - [3.14 dropse](#314-dropse)
  - [3.15 rename](#315-rename)
  - [3.16 randbase](#316-randbase)
  - [3.17 cutN](#317-cutN)
  - [3.18 gap ](#318-gap-)
  - [3.19 telo](#319-telo)
  - [3.20 tutorial](#320-tutorial)
- [4 Reference](#4-Reference)

***

## 1 Introduce

### 1.1 Seqtk

`Seqtk` is a fast and lightweight tool for processing sequences in the FASTA or FASTQ format. It seamlessly parses both `FASTA` and `FASTQ` files which can also be optionally compressed by gzip[^1].&#x20;

> `Seqtk`是一个快速且轻量级的工具，用于处理 FASTA 或 FASTQ 格式的序列数据。它能够无缝地解析这两种格式的文件，这些文件还可以选择性地通过 gzip 进行压缩处理。

***

## 2 Install

### 2.1 install by source

```bash title="install by source"
git clone https://github.com/lh3/seqtk.git
cd seqtk; make
```


### 2.2 install by conda

```r title="install by conda"
mamba install -c bioconda seqtk
```


***

## 3 Tutorial

### 3.1 fastq → fasta

> `seq`   : FASTA/Q格式转换
>
> ```bash title="seq parameter"
> -q INT  # 掩蔽碱基质量低于INT的碱基
> -X INT  # 掩蔽碱基质量高于INT的碱基
> -L INT  # 移除序列长度短于INT的序列
> -Q INT  # fastq文件质量编码切换 
> -A      # 强制FASTA输出
> -C      # 移除fasta文件中的注释信息
> ```
>
>
> ```bash title="fastq → fasta"
> seqtk seq -A input.fastq > output.fasta
>
>
>
> ```
>

### 3.2 FASTQ Size

> `size` : fastq文件中read数量与碱基数量快速统计命令
>
> ```bash 
> seqtk size SRR13016548_1.fastq.gz
> 24345228        2458868028
> ```
>

### 3.3 FASTA comp

> `comp`：对fasta文件中特定序列长度 & 碱基含量 & CpG & tv & ts 参数进行快速统计

```bash title="FASTA comp"
Usage:  seqtk comp [-u] [-r in.bed] <in.fa>
Output format: chr, length, #A, #C, #G, #T, #2, #3, #4, #CpG, #tv, #ts, #CpG-ts
```


> **NOTE** : 提取出的结果可以搭配`cat`等命令进行进一步处理。

### 3.4 Downsample

> `sample`：对fastq文件中的read进行子集化,也可以对fastq文件进行downsample[^2]。

```bash title="sample parameter"
-s INT  # 随机种子
-2      # 2-pass mode: 减少内存使用但耗时可能多一些
```


```r title="random extert seq form fastq & fasta"
# Subsample 10000 read pairs from two large paired FASTQ files (remember to use the same random seed to keep pairing):
# random extert seq form fastq & fasta
seqtk sample -s100 read1.fq 10000 > sub1.fq
seqtk sample -s100 read1.fa 10000 > sub2.fa
```


### 3.5 subseq

> `subseq`: 提取`fasta`文件中特定序列，也可以使用bed文件对批量特定区域进行提取

```bash title="seqtk subseq"
seqtk subseq [options] <in.fa> <in.bed>|<name.list>
```


```bash title="parameter"
-t     # TAB 分割的输出

```


> **NOTE** : 在对fa文件进行提取前可以使用`samtools faidx`建立`index`

### 3.6 fqchk

> `fqchk`：fastq文件质量快速检查

```bash title="command"
fastq seqtk fqchk SRR13016548_1.fastq.gz > SRR13016548_1.qc
```


```bash title="fastq seqtk result"
min_len: 101; max_len: 101; avg_len: 101.00; 7 distinct quality values
POS  #bases  %A  %C  %G  %T  %N  avgQ  errQ  %low  %high
ALL  2458868028  23.3  25.5  25.2  25.9  0.0  39.2  29.5  1.4  98.6
1  24345228  7.7  46.5  37.6  8.2  0.0  31.5  27.7  1.6  98.4
2  24345228  11.7  25.4  23.8  39.1  0.0  31.6  28.3  1.3  98.7
3  24345228  14.6  38.1  25.8  21.5  0.0  35.4  28.6  1.5  98.5
4  24345228  23.9  27.1  28.4  20.6  0.0  35.9  29.0  1.5  98.5
5  24345228  26.8  20.1  29.0  24.1  0.0  36.4  30.7  0.9  99.1
6  24345228  29.0  22.0  24.3  24.7  0.0  39.8  32.1  0.7  99.3
7  24345228  21.8  18.7  19.3  40.1  0.0  40.0  32.4  0.7  99.3
8  24345228  20.3  25.4  22.2  32.1  0.0  39.9  32.2  0.7  99.3
9  24345228  19.4  24.8  20.9  34.9  0.0  40.1  32.8  0.6  99.4
10  24345228  31.9  19.7  23.0  25.5  0.0  40.0  32.5  0.6  99.4
11  24345228  23.7  26.5  27.9  22.0  0.0  40.1  33.1  0.5  99.5
12  24345228  20.8  26.1  25.9  27.1  0.0  39.8  31.4  0.9  99.1
13  24345228  22.3  25.3  25.2  27.2  0.0  39.8  31.4  0.8  99.2
14  24345228  23.5  24.5  24.4  27.7  0.0  39.8  31.5  0.8  99.2
15  24345228  23.1  25.1  25.1  26.7  0.0  39.8  31.4  0.9  99.1
16  24345228  23.2  25.2  25.7  25.8  0.0  39.6  31.0  0.9  99.1
17  24345228  23.7  24.5  25.5  26.4  0.0  39.9  31.9  0.7  99.3
18  24345228  23.4  25.4  25.1  26.2  0.0  39.9  31.9  0.8  99.2
19  24345228  23.5  25.2  25.6  25.6  0.0  39.7  31.1  0.9  99.1
20  24345228  23.7  24.6  25.2  26.4  0.0  39.6  30.5  1.1  98.9
21  24345228  23.3  25.3  25.1  26.3  0.0  39.9  31.9  0.7  99.3
22  24345228  23.6  25.3  25.3  25.8  0.0  39.9  32.2  0.7  99.3
23  24345228  23.7  24.5  25.1  26.7  0.0  39.7  31.2  0.9  99.1
24  24345228  23.6  25.1  24.9  26.4  0.0  39.7  31.2  0.9  99.1
25  24345228  23.7  25.3  25.4  25.6  0.0  39.7  31.0  1.0  99.0
26  24345228  24.1  24.5  25.1  26.3  0.0  39.6  29.8  1.2  98.8
27  24345228  23.5  25.5  24.9  26.1  0.0  39.6  30.1  1.2  98.8
28  24345228  23.5  25.6  25.2  25.6  0.0  39.6  29.9  1.3  98.7
29  24345228  23.8  24.8  25.1  26.3  0.0  39.6  30.1  1.2  98.8
30  24345228  23.4  25.6  25.0  26.0  0.0  39.5  29.4  1.5  98.5
31  24345228  23.6  25.6  25.4  25.4  0.0  39.5  29.8  1.3  98.7
32  24345228  23.9  24.8  24.9  26.4  0.0  39.6  30.0  1.2  98.8
33  24345228  23.4  25.6  24.9  26.1  0.0  39.4  29.4  1.5  98.5
34  24345228  23.6  25.6  25.3  25.5  0.0  39.6  30.0  1.3  98.7
35  24345228  23.8  24.9  25.2  26.2  0.0  39.6  30.1  1.2  98.8
36  24345228  23.4  25.6  25.1  25.9  0.0  39.6  30.2  1.2  98.8
37  24345228  23.6  25.6  25.5  25.4  0.0  39.5  29.5  1.4  98.6
38  24345228  24.0  24.8  25.2  26.0  0.0  39.5  29.8  1.3  98.7
39  24345228  23.6  25.4  25.2  25.8  0.0  39.2  27.7  2.3  97.7
40  24345228  23.5  25.6  25.4  25.5  0.0  39.4  29.6  1.3  98.7
41  24345228  23.7  24.9  25.2  26.2  0.0  39.6  30.0  1.2  98.8
42  24345228  23.3  25.5  24.9  26.2  0.0  39.6  30.3  1.2  98.8
43  24345228  23.4  25.5  25.4  25.7  0.0  39.7  30.1  1.1  98.9
44  24345228  23.7  24.8  25.1  26.3  0.0  39.6  29.9  1.3  98.7
45  24345228  23.3  25.5  25.0  26.2  0.0  39.6  29.8  1.3  98.7
46  24345228  23.5  25.7  25.4  25.4  0.0  39.5  29.5  1.4  98.6
47  24345228  23.9  24.9  25.0  26.2  0.0  39.5  29.7  1.4  98.6
48  24345228  23.3  25.7  25.1  25.9  0.0  39.4  29.1  1.6  98.4
49  24345228  23.5  25.6  25.5  25.4  0.0  39.4  29.4  1.5  98.5
50  24345228  23.8  25.0  25.2  26.0  0.0  39.3  28.6  1.8  98.2
51  24345228  23.4  25.7  25.0  25.9  0.0  39.5  29.4  1.4  98.6
52  24345228  23.6  25.6  25.4  25.4  0.0  39.4  29.0  1.6  98.4
53  24345228  23.8  24.9  25.1  26.1  0.0  39.4  29.0  1.6  98.4
54  24345228  23.4  25.6  24.9  26.0  0.0  39.5  29.3  1.5  98.5
55  24345228  23.5  25.6  25.4  25.5  0.0  39.5  29.6  1.4  98.6
56  24345228  23.9  24.9  25.1  26.1  0.0  39.3  28.7  1.8  98.2
57  24345228  23.2  25.7  25.1  25.9  0.0  39.4  29.1  1.6  98.4
58  24345228  23.4  25.7  25.5  25.4  0.0  39.4  28.9  1.6  98.4
59  24345228  23.8  24.9  25.2  26.1  0.0  39.3  28.8  1.7  98.3
60  24345228  23.4  25.7  25.0  25.9  0.0  39.3  28.9  1.7  98.3
61  24345228  23.6  25.6  25.4  25.3  0.0  39.4  29.1  1.6  98.4
62  24345228  24.0  25.0  24.9  26.1  0.0  39.2  28.3  1.9  98.1
63  24345228  23.5  25.6  25.0  25.9  0.0  39.1  28.2  2.0  98.0
64  24345228  23.5  25.8  25.3  25.3  0.0  38.8  27.5  2.4  97.6
65  24345228  24.0  24.9  25.1  26.0  0.0  39.1  28.2  1.9  98.1
66  24345228  23.4  25.7  25.1  25.9  0.0  39.2  28.5  1.8  98.2
67  24345228  23.5  25.6  25.5  25.4  0.0  39.1  28.3  1.9  98.1
68  24345228  23.8  25.0  25.1  26.0  0.0  38.9  28.0  2.1  97.9
69  24345228  23.4  25.6  25.1  25.9  0.0  38.9  27.8  2.2  97.8
70  24345228  23.5  25.6  25.5  25.4  0.0  38.9  27.8  2.2  97.8
71  24345228  23.8  25.1  25.1  25.9  0.0  38.9  27.9  2.2  97.8
72  24345228  23.4  25.7  25.0  25.9  0.0  38.9  27.8  2.2  97.8
73  24345228  23.5  25.8  25.4  25.3  0.0  38.9  27.8  2.2  97.8
74  24345228  23.8  25.0  25.2  26.0  0.0  38.9  27.7  2.2  97.8
75  24345228  23.4  25.8  25.0  25.8  0.0  38.9  27.5  2.2  97.8
76  24345228  23.6  25.8  25.4  25.2  0.0  39.0  27.9  2.1  97.9
77  24345228  23.9  24.9  25.2  25.9  0.0  37.2  28.7  1.5  98.5
78  24345228  23.4  25.6  25.0  25.9  0.0  38.9  29.5  1.4  98.6
79  24345228  23.6  25.7  25.4  25.4  0.0  39.4  30.0  1.2  98.8
80  24345228  23.8  25.2  25.3  25.8  0.0  39.5  29.6  1.4  98.6
81  24345228  23.5  25.7  24.9  25.9  0.0  39.6  30.0  1.3  98.7
82  24345228  23.6  25.7  25.3  25.3  0.0  39.7  30.5  1.1  98.9
83  24345228  23.8  25.1  25.1  26.0  0.0  39.7  30.3  1.1  98.9
84  24345228  23.5  25.6  25.1  25.8  0.0  39.7  30.3  1.2  98.8
85  24345228  23.5  25.8  25.5  25.2  0.0  39.7  30.3  1.2  98.8
86  24345228  23.8  25.0  25.2  25.9  0.0  39.7  30.1  1.2  98.8
87  24345228  23.6  25.7  25.0  25.7  0.0  39.7  30.1  1.2  98.8
88  24345228  23.6  25.8  25.4  25.1  0.0  39.6  29.7  1.3  98.7
89  24345228  24.0  25.0  25.2  25.8  0.0  39.6  29.9  1.3  98.7
90  24345228  23.5  25.6  25.1  25.7  0.0  39.6  29.8  1.3  98.7
91  24345228  23.7  25.8  25.3  25.2  0.0  39.6  29.5  1.4  98.6
92  24345228  24.0  25.1  25.1  25.8  0.0  39.5  29.6  1.4  98.6
93  24345228  23.5  25.7  25.0  25.7  0.0  39.5  29.6  1.4  98.6
94  24345228  23.9  25.7  25.3  25.1  0.0  39.5  29.2  1.5  98.5
95  24345228  24.1  25.1  25.2  25.7  0.0  39.5  29.4  1.5  98.5
96  24345228  23.6  25.7  25.0  25.6  0.0  39.4  29.3  1.5  98.5
97  24345228  23.7  25.8  25.5  25.0  0.0  39.4  29.2  1.5  98.5
98  24345228  24.1  25.0  25.3  25.6  0.0  39.3  28.6  1.8  98.2
99  24345228  23.6  25.7  25.2  25.5  0.0  39.3  28.7  1.7  98.3
100  24345228  23.8  25.6  25.5  25.1  0.0  39.3  28.8  1.7  98.3
101  24345228  24.1  25.1  25.3  25.4  0.0  38.3  26.9  2.7  97.3
```


### `3.7 mergepe`

> `mergepe`将两个成对的FASTQ或FASTA文件（即paired-end reads文件）合并成一个单一的文件，其中每一对序列的顺序保持不变。

```bash title="mergepe"
Usage: seqtk mergepe <in1.fq> <in2.fq>
```


### 3.8 split

> `split` : 将一个fa文件拆分为多个文件

```bash title="seqtk split"
Usage: seqtk split [options] <prefix> <in.fa>
Options:
  -n INT    number of files [10]
  -l INT    line length [0]
```


### 3.9 trimfq&#x20;

> `trimfq` : 更具Phred algorithm对FASTQ文件进行trim

```bash title="parameter"
-q FLOAT    error rate threshold (disabled by -b/-e) [0.05]
-l INT      maximally trim down to INT bp (disabled by -b/-e) [30]
-b INT      trim INT bp from left (non-zero to disable -q/-l) [0]
-e INT      trim INT bp from right (non-zero to disable -q/-l) [0]
-L INT      retain at most INT bp from the 5'-end (non-zero to disable -q/-l) [0]
-Q          force FASTQ output
```


### 3.10 hety&#x20;

> `hety` : 区域杂合性鉴定
>
> ```bash title="command"
> Usage:   seqtk hety [options] <in.fa>
> -w INT   # window size [50000]
> -t INT   # start positions in a window [5]
> -m       # treat lowercases as masked
> ```
>

### 3.11 gc

> `gc`：fa文件中高与低GC区域鉴定
>
> ```bash title="command"
> Usage: seqtk gc [options] <in.fa>
> Options:
>   -w         identify high-AT regions
>   -f FLOAT   min GC fraction (or AT fraction for -w) [0.60]
>   -l INT     min region length to output [20]
>   -x FLOAT   X-dropoff [10.0]
> ```
>

### 3.12 mutfa

> `mutfa` : `fasta`文件中特定位点点突变
>
> ```bash title="command"
> Usage: seqtk mutfa <in.fa> <in.snp>
> Note: <in.snp> contains at least four columns per line which are:
>       'chr  1-based-pos  any  base-changed-to'.
> ```
>

### 3.13 mergefa

> `mergefa` : 合并两个fa文件

```bash 
Usage: seqtk mergefa [options] <in1.fa> <in2.fa>
-q INT   quality threshold [0]
-i       take intersection
-m       convert to lowercase when one of the input base is N
-r       pick a random allele from het
-h       suppress hets in the input
```


### 3.14 dropse

> `dropse`:移除`mergepe`合并获得的fq文件中不匹配的read

```bash title="dropse"
Usage: seqtk dropse <in.fq>
```


### 3.15 rename

> `rename` : fq文件重命名

```bash title="rename"
Usage: seqtk rename <in.fq> [prefix]
```


### 3.16 randbase

> `randbase` ： 从杂合位点（hets）中随机选择碱基

### 3.17 cutN

> `cutN`: 切割长度大于N的序列

### 3.18 gap&#x20;

> `gap` ： 获取gap 位点

### 3.19 telo

> `telo`  ： 从asm or long reads中识别端粒重复

### 3.20 tutorial

```bash title="提取fa文件中长度小于71的read"
seqtk seq -A SQ24050610-K54-1-CRISPR-lib-K54_combined_R1_tso_fp_paird.fa | awk 'BEGIN {RS=">"; ORS=""} length($2) < 71 {print ">" $0}' > SQ24050610-K54-1-CRISPR-lib-K54_combined_R1_tso_fp_paird_short.fa
```


```bash title="提取fa文件中长度大于70的read"
seqtk seq -A SQ24050610-K54-1-CRISPR-lib-K54_combined_R1_tso_fp_paird.fa | awk 'BEGIN {RS=">"; ORS=""} length($2) > 70 {print ">" $0}' > SQ24050610-K54-1-CRISPR-lib-K54_combined_R1_tso_fp_paird_long.fa
```


```bash title="统计fa文件中序列的长度   ATGC含量"
seqtk comp SQ24050610-K54-1-CRISPR-lib-K54_combined_R1_tso_fp_paird_long_cut_tso_fb.fa | awk -F'\t' '{print $1 "\t" $2}'
```


```r 
# 定义输入文件
input_file="SQ24054190-K54-1-CRISPR-lib-K54_combined_R1.tso.fp.fa"
# 定义正则表达式模式
pattern="TTTCTTATATGGG.*AATAAGGCTAGTCCGTTATCAACTTG"
# 提取匹配模式的序列ID
seqtk subseq ${input_file} <(grep -E -B1 "${pattern}" ${input_file} | grep "^>" | sed 's/>//') > matched_sequences.fa

```


```r 
seqtk seq -L 80 matched_sequences.fa > filtered_sequences.long.fa
seqtk seq -L 1 -U 78 matched_sequences.fa > filtered_sequences.short.fa

```


***

## 4 Reference

[^1]: [https://github.com/lh3/seqtk](https://github.com/lh3/seqtk "https://github.com/lh3/seqtk")

[^2]: [https://onestopdataanalysis.com/subsample-paired-fastq-fasta/](https://onestopdataanalysis.com/subsample-paired-fastq-fasta/ "https://onestopdataanalysis.com/subsample-paired-fastq-fasta/")
