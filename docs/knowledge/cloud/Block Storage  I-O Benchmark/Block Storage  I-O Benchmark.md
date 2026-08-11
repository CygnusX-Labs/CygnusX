# Block Storage  I/O Benchmark

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 Block Storage  I/O  Benchmark](#11-Block-Storage--IO--Benchmark)
  - [1.2 fio](#12-fio)
- [2 Install](#2-Install)
  - [2.1 Install form Source ](#21-Install-form-Source-)
  - [2.2 Install form Binary](#22-Install-form-Binary)
- [3 Tutorial](#3-Tutorial)
  - [3.1 Block Storage  I/O Benchmark](#31-Block-Storage--IO-Benchmark)
  - [3.2 fio Result](#32-fio-Result)
    - [3.2.1 FIO Parameter](#321-FIO-Parameter)
- [4 Source](#4-Source)
- [5 Reference](#5-Reference)

## 1 Introduce

### 1.1 Block Storage  `I/O`  Benchmark

通过测试块存储性能，可以帮助您更好地理解存储设备的能力，并对其进行相应的优化和调整，以确保最佳性能。测试裸盘可以获得较为真实的块存储性能，本文将介绍如何在`Linux`系统中使用开源测试工具`FIO`测试裸盘的关键性能指标，包括`IOPS`（每秒输入/输出操作次数）、吞吐量（数据传输速率）和时延（响应时间）[^1]。

### `1.2 fio`

`fio` 是一款 用于对磁盘进行性能测试的工具。可以测试`IOPS`，吞吐量，`I/O`延迟等主要性能指标,而且支持多种`I/O`引擎。`fio`支持13种不同的`I/O`引擎，包括:`sync`,`mmap`, `libaio`, `posixaio`, `SG v3`, `splice`, `null`, `network`, `syslet`, `guasi`, `solarisaio` 等[^2]。

## 2 Install

### 2.1 Install form Source&#x20;

```bash title="source "
# download fio source 
wget https://github.com/axboe/fio/archive/refs/tags/fio-3.39.zip
unzip fio-3.39.zip
cd /fio-fio-3.39
make && make install
```


```bash title="fio"
# fio version
./fio -v
fio-3.39
```


### 2.2 Install form Binary

```bash title="CentOS"
# CentOS
sudo yum install libaio libaio-devel fio -y
```


```bash title="Debain & Ubuntu"
# Debain & Ubuntu
sudo apt-get update
apt-get install gnuplot -y
sudo apt-get install fio -y
```


## 3 Tutorial

### 3.1 Block Storage  I/O Benchmark

```bash title="查询块存储的设备名称"
# 查询块存储的设备名称
sudo fdisk -lu
# 查询块存储的设备名称
sudo blkid
```


```bash title="测试云盘的随机写IOPS"
# 测试云盘的随机写IOPS
sudo fio -direct=1 -iodepth=128 \
         -rw=randwrite -ioengine=libaio \
         -bs=4k -size=1G -numjobs=1 -runtime=1000 \
         -group_reporting -filename=/dev/your_device -name=Rand_Write_Testing
```


```bash title="测试云盘的随机读IOPS"
# 测试云盘的随机读IOPS
sudo fio -direct=1 -iodepth=128 \
     -rw=randread -ioengine=libaio \
     -bs=4k -size=1G -numjobs=1 -runtime=1000 \
     -group_reporting -filename=/dev/your_device -name=Rand_Read_Testing
```


```bash title="测试云盘的顺序写吞吐量"
# 测试云盘的顺序写吞吐量
sudo fio -direct=1 -iodepth=64 \
     -rw=write -ioengine=libaio \
     -bs=1024k -size=1G -numjobs=1 \
     -runtime=1000 -group_reporting -filename=/dev/your_device \
     -name=Write_PPS_Testing

```


```bash title="测试云盘的顺序读吞吐量"
# 测试云盘的顺序读吞吐量
sudo fio -direct=1 -iodepth=64 \
     -rw=read -ioengine=libaio \
     -bs=1024k -size=1G -numjobs=1 \
     -runtime=1000 -group_reporting -filename=/dev/your_device \
     -name=Read_PPS_Testing

```


```bash title="测试云盘的随机写时延"
# 测试云盘的随机写时延
sudo fio -direct=1 -iodepth=1 -rw=randwrite \
     -ioengine=libaio -bs=4k -size=1G -numjobs=1 \
     -group_reporting -filename=/dev/your_device \
     -name=Rand_Write_Latency_Testing

```


```bash title="测试云盘的随机读时延"
# 测试云盘的随机读时延
sudo fio -direct=1 -iodepth=1 \
     -rw=randread -ioengine=libaio -bs=4k -size=1G \
     -numjobs=1 -group_reporting -filename=/dev/your_device \
     -name=Rand_Read_Latency_Testing
     write_bw_log=rw write_lat_log=rw write_iops_log=rw
```


### `3.2 fio` Result

**`IOPS`**： 每秒完成的 `I/O` 操作次数（以实际的`bs`大小为单位）

**带宽（****`Bandwidth, BW`****）** ： 单位时间内数据传输量（通常为 `MB/s` 或 `GB/s`）

**延迟（Latency）**

- **`slat`（提交延迟）**：从请求提交到内核的时间。
- **`clat`（完成延迟）**：从内核到请求完成的时间（**最核心的 ****`I/O`**** 响应时间指标**）。
- **`lat`（总延迟）**：`slat + clat`。

![](<image/截屏2025-02-23 00.43.02_aQWrdyfyqk.png>)

#### 3.2.1 FIO Parameter

| **参数**​              | **说明**​                                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| \`direct\`           | 表示是否使用\`direct I/O\`。默认值：1。  - 值为1：表示使用\`direct I/O\`，忽略\`I/O\`缓存，数据直接写入。 - 值为0：表示不使用\`direct I/O\`。                                                                |
| \`iodepth\`          | 表示测试时的IO队列深度。例如\`-iodepth=128\`表示FIO控制请求中的I/O最大个数为128。                                                                                                              |
| \`rw\`               | 表示测试时的读写策略。您可以设置为：  - \`randwrite\`：随机写。 - \`randread\`：随机读。 - \`read\`：顺序读。 - \`write\`：顺序写。 - \`randrw\`：混合随机读写。                                                  |
| \`ioengine\`         | 表示测试时\`FIO\`选择哪种\`I/O\`引擎，通常选择\`libaio\`，更符合日常应用模式。                                                                                                                 |
| \`bs\`               | \`I/O\`单元的块大小（\`block size\`）。默认值：4 KiB。读取和写入的值可以以\`read\`、\`write\`格式单独指定，其中任何一个都可以为空以将该值保留为其默认值。                                                                  |
| \`size\`             | 测试文件大小 : \`FIO\`会将指定的文件大小全部读/写完成，然后才停止测试，除非受到其他选项（例如运行时）的限制。如果未指定该参数，\`FIO\`将使用给定文件或设备的完整大小。也可以将大小作为1到100之间的百分比给出。例如指定\`size=20%\`，\`FIO\`将使用给定文件或设备完整大小的\`20%\`空间。 |
| \`numjobs\`          | 测试的并发线程数。默认值：1。                                                                                                                                                     |
| \`runtime\`          | \`FIO\`运行时长：如果未指定该参数，则\`FIO\`会持续将上述\`size\`指定大小的文件，以每次bs值为块大小读/写完成。                                                                                                 |
| \`group\_reporting\` | 测试结果显示模式 : 如果指定该参数，测试结果会汇总每个进程的统计信息，而不是以不同任务来统计信息。                                                                                                                  |
| \`filename\`         | 待测试的对象路径，路径可以是云盘设备名称或者一个文件地址。                                                                                                                                       |
| \`name\`             | 表示测试任务名称，可以随意设定。例如本示例的\`Rand\_Write\_Testing\`。                                                                                                                     |

## 4 Source

> \*\*`fio`\*\***使用教程:**
>
> [ fio使用教程 | 李厅 FIO 是一款 用于对磁盘进行性能测试的工具。可以测试IOPS，吞吐量，IO延迟等主要性能指标,而且支持多种IO引擎。FIO支持13种不同的I/O引擎，包括:sync,mmap, libaio, posixaio, SG v3, splice, null, network, syslet, guasi, solarisaio 等等。由于目前主要做ceph的项目，所有搜索引擎主要使用rbd，下面的例 https://lovethegirl.github.io/2019/12/04/fio/](https://lovethegirl.github.io/2019/12/04/fio/ " fio使用教程 | 李厅 FIO 是一款 用于对磁盘进行性能测试的工具。可以测试IOPS，吞吐量，IO延迟等主要性能指标,而且支持多种IO引擎。FIO支持13种不同的I/O引擎，包括:sync,mmap, libaio, posixaio, SG v3, splice, null, network, syslet, guasi, solarisaio 等等。由于目前主要做ceph的项目，所有搜索引擎主要使用rbd，下面的例 https://lovethegirl.github.io/2019/12/04/fio/")

## 5 Reference

[^1]: [https://help.aliyun.com/zh/ecs/user-guide/test-the-performance-of-block-storage-devices?spm=a2c4g.11186623.help-menu-25365.d\_4\_3\_5\_2.634e27f32boG6U#da4ea1a6ad59y](https://help.aliyun.com/zh/ecs/user-guide/test-the-performance-of-block-storage-devices?spm=a2c4g.11186623.help-menu-25365.d_4_3_5_2.634e27f32boG6U#da4ea1a6ad59y "https://help.aliyun.com/zh/ecs/user-guide/test-the-performance-of-block-storage-devices?spm=a2c4g.11186623.help-menu-25365.d_4_3_5_2.634e27f32boG6U#da4ea1a6ad59y")

[^2]: [https://lovethegirl.github.io/2019/12/04/fio/](https://lovethegirl.github.io/2019/12/04/fio/ "https://lovethegirl.github.io/2019/12/04/fio/")
