# Trimmomatic

## 目录

- [1 Introduce](#1-Introduce)
- [2 install](#2-install)
- [3 tutorial](#3-tutorial)
- [4 question](#4-question)
  - [4.1 dropped fastq file](#41-dropped-fastq-file)
- [5 Source](#5-Source)
- [6 Reference](#6-Reference)

```r 
# author  : zhang jian
# date    : 2024.1.12
# version : 1.0v
# description : this is raw fastq deal tutorial
```


***

## 1 Introduce

***Trimmomatic*** for Illumina sequence data.[^1]

***

## 2 install

```r 
conda install bioconda::trimmomatic -y
```


***

## 3 tutorial

***Trimmomatic***  可以对PE & SE的read进行处理！

```r 
trimmomatic PE [-version] [-threads <threads>] [-phred33|-phred64] [-trimlog <trimLogFile>] [-summary <statsSummaryFile>] [-quiet] [-validatePairs] [-basein <inputBase> | <inputFile1> <inputFile2>] [-baseout <outputBase> | <outputFile1P> <outputFile1U> <outputFile2P> <outputFile2U>] <trimmer1>...
```


```r 
trimmomatic SE [-version] [-threads <threads>] [-phred33|-phred64] [-trimlog <trimLogFile>] [-summary <statsSummaryFile>] [-quiet] <inputFile> <outputFile> <trimmer1>...
```


***

## 4 question

### 4.1 dropped fastq file

When trimming reads from a fastq file, some reads are naturally dropped. For example, an entire read may be trimmed so that there is nothing left, or the read remaining after trimming may be shorter than the minimum length requirement for keeping it. In the case of single-end (SE) sequencing, the consequences are simple: reads are simply dropped from the results file. In the case of PE sequencing, if one read of a mate pair is dropped, then the other read is *orphaned*. Trimmomatic produces separate files for the surviving pairs and for the surviving orphans (four files in total).[^2]

> PE测序方法获得的R1& R2中的序列是匹配的，而当使用trimmomatic对其进行处理时，由于质量较差OR 修剪后的长度小于最低要求，一部分read会被移除，这在SE测序中并不会产生较大的影响，而对于PE测序而言会导致一些read成为dropped序列！

> 在使用trimmomatic对raw fatsq序列进行质控时，可能会产生dropped.fastq文件！ Only for PE read。

```r 
# dropped.fastq.gz is 
R20042888LR01-S111-_R1.dropped.fastq.gz
R20042888LR01-S111-_R1.trimmed.fastq.gz
R20042888LR01-S111-_R2.dropped.fastq.gz
R20042888LR01-S111-_R2.trimmed.fastq.gz
```


***

## 5 Source

[ Genomic Data Analysis: NGS data wrangling on the command line: Trimming reads  https://gtk-teaching.github.io/NGS-intro/03-trimming/index.html](https://gtk-teaching.github.io/NGS-intro/03-trimming/index.html " Genomic Data Analysis: NGS data wrangling on the command line: Trimming reads  https://gtk-teaching.github.io/NGS-intro/03-trimming/index.html")

[Trimmomatic a flexible trimmer for Illumina sequence data.pdf](<file/Trimmomatic a flexible trimmer for Illumina sequen.pdf> "Trimmomatic a flexible trimmer for Illumina sequence data.pdf")

***

## 6 Reference

[^1]: Trimmomatic: a flexible trimmer for Illumina sequence data

[^2]: [https://gtk-teaching.github.io/NGS-intro/03-trimming/index.html](https://gtk-teaching.github.io/NGS-intro/03-trimming/index.html "https://gtk-teaching.github.io/NGS-intro/03-trimming/index.html")
