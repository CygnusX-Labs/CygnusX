# refFlat

gtf转换成refFlat

```bash 
# install ucsc-gtftogenepred by conda
conda install -c bioconda ucsc-gtftogenepred -y
```


```bash 
# gtf2refFlat
gtfToGenePred -genePredExt -geneNameAsName2 genes.gtf refFlat.tmp.txt
paste <(cut -f 12 refFlat.tmp.txt) <(cut -f 1-10 refFlat.tmp.txt) > refFlat.txt
```
