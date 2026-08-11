# Skewer

```r 
mamba install bioconda::skewer  -y
```


```bash 
skewer \
-m pe \
-f sanger \
-r 0.1 \
-d 0.03 \
-q 20 \
-Q 20 \
-l 75 \
-n \
-o ${prefix} \
--quiet \
--compress \
-X \
-t 10 \
${prefix}_R1.fastq.gz \
${prefix}_R2.fastq.gz
```


[Skewer- a fast and accurate adapter trimmer for next-generation sequencing paired-end reads.pdf](<file/Skewer- a fast and accurate adapter trimmer for ne.pdf> "Skewer- a fast and accurate adapter trimmer for next-generation sequencing paired-end reads.pdf")
