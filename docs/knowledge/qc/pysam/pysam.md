# pysam

## 目录

- [1 introduce](#1-introduce)
  - [1.1 Pysam](#11-Pysam)
- [2 install](#2-install)
- [3 tutorial](#3-tutorial)
- [4 Source](#4-Source)
- [5 Reference](#5-Reference)

***

## 1 introduce

### 1.1 Pysam

`Pysam` is a python module for **reading**, **manipulating** and **writing** genomic data sets[^1].

> `Pysam`是一个基于**htslib**的C语言应用程序编程接口(C-API) ,提供了读写多种生物信息学文件格式的功能，包括序列对齐格式(SAM)、二进制序列对齐格式(BAM)、变异调用格式(VCF)、二进制变异调用格式(BCF)、浏览器可扩展数据(BED)、基因组特征格式(GFF)、基因组传输格式(GTF)、核酸序列(FASTA)和快速质量(FASTQ)文件,同时支持通过索引进行压缩和随机访问。

> 当前`Pysam`包内置了`htslib-1.18`  & `samtools-1.18`\* *&* \*`bcftools-1.18`

## 2 install

```bash 

```


## 3 tutorial

[SAM/BAM](https://www.wolai.com/5QdGYm1L277TSuryCgAm8X "SAM/BAM")

`vcf_in.header.contigs.keys()`

pysam & vcf

```bash 
from pysam import VariantFile
vcf  = '/titan3/lin_jie/project/phrama/202401_WGS_val/VAL_542_val/giab_reference/HG002_NA24385/SV/HG002_SVs_Tier1_v0.6.vcf.gz'
vcf_file = vcf # 替换为你的VCF文件路径
vcf_in = VariantFile(vcf_file)
print(vcf_in.header)


```


```bash 
chromosomes =  ['1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','X','Y']
# for chrom in chromosomes:
#    vcf_in.header.contigs.add(chrom)
```


```bash 
vcf_in.header.contigs.add(ID,length=None)
add(id, length=None, **kwargs) method of pysam.libcbcf.VariantHeaderContigs instance

  VariantHeaderContigs.add(self, id, length=None, **kwargs)

  Add a new contig record
```


```bash 
# chr_chromosomes =  ['chr1','chr2','chr3','chr4','chr5','chr6','chr7','chr8','chr9','chr10','chr11','chr12','chr13','chr14','chr15','chr16','chr17','chr18','chr19','chr20','chr21','chr22','chrX','chrY']
# for chrom in chr_chromosomes:
#   vcf_in.header.contigs.add(chrom)
```


```bash 
output_vcf = "/titan3/local_zhang_jian/mutation_sv/benchmark/benchmark/HG002_SVs_chr1_chry_remove_lt50bp_only_CGcalls_HG2count.vcf"
vcf_out = VariantFile(output_vcf, 'w', header=vcf_in.header)
# 迭代VCF文件中的记录并过滤
for record in vcf_in.fetch():
    if record.chrom in chromosomes and 'lt50bp' not in record.filter and record.info.get('CGcalls') != 0 and record.info.get('HG2count') != 0:
        vcf_out.write(record)
vcf_out.close()
```


## 4 Source

> \*\*Pysam offiice web : \*\*
>
> [ pysam: htslib interface for python — pysam 0.22.1 documentation  https://pysam.readthedocs.io/en/latest/index.html#](https://pysam.readthedocs.io/en/latest/index.html# " pysam: htslib interface for python — pysam 0.22.1 documentation  https://pysam.readthedocs.io/en/latest/index.html#")

## 5 Reference

[^1]: [https://pysam.readthedocs.io/en/latest/index.html](https://pysam.readthedocs.io/en/latest/index.html "https://pysam.readthedocs.io/en/latest/index.html")
