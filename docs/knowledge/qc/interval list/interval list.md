# interval list

Picard-style interval files have a SAM-like header that includes a sequence dictionary. The intervals are given in the form `<chr>:<start>-<stop> + <target_name>`, with fields separated by tabs, and the coordinates are 1-based (first position in the genome is position 1, not position 0).

```r 
# Example  interval files
@HD     VN:1.0  SO:coordinate
@SQ     SN:1    LN:249250621    AS:GRCh37       UR:http://www.broadinstitute.org/ftp/pub/seq/references/Homo_sapiens_assembly19.fasta   M5:1b22b98cdeb4a9304cb5d48026a85128     SP:Homo Sapiens
@SQ     SN:2    LN:243199373    AS:GRCh37       UR:http://www.broadinstitute.org/ftp/pub/seq/references/Homo_sapiens_assembly19.fasta   M5:a0d9851da00400dec1098a9255ac712e     SP:Homo Sapiens
1       30366   30503   +       target_1
1       69089   70010   +       target_2
1       367657  368599  +       target_3
1       621094  622036  +       target_4
1       861320  861395  +       target_5
1       865533  865718  +       target_6
```


fasta → interval list

[ 从 fasta 创建用于 GATK 流程的 interval list GATKbundle 提供了用于 WGS 的 interval list 文件，但如果你用的参考基因组跟他提供的 interval list 不一致，比方说 Contig 命... https://www.jianshu.com/p/3982ea467976](https://www.jianshu.com/p/3982ea467976 " 从 fasta 创建用于 GATK 流程的 interval list GATKbundle 提供了用于 WGS 的 interval list 文件，但如果你用的参考基因组跟他提供的 interval list 不一致，比方说 Contig 命... https://www.jianshu.com/p/3982ea467976")
