# AWS S3

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 AWS S3](#11-AWS-S3)
  - [1.2 AWS S3 Features](#12-AWS-S3-Features)
- [2 Tutorial](#2-Tutorial)
  - [2.1 AWS CLI](#21-AWS-CLI)
    - [2.1.1 Install aws cli](#211-Install-aws-cli)
    - [2.1.2 configure aws](#212-configure-aws)
    - [2.1.3 aws command](#213-aws-command)
      - [2.1.3.1 Create bucket](#2131-Create-bucket)
      - [2.1.3.2 list bucket or object](#2132-list-bucket-or-object)
      - [2.1.3.3 delete bucket](#2133-delete-bucket)
      - [2.1.3.4 Delete object](#2134-Delete-object)
      - [2.1.3.5 move object](#2135-move-object)
      - [2.1.3.6 copy object](#2136-copy-object)
      - [2.1.3.7 sync object](#2137-sync-object)
  - [2.2 Download SRA Data](#22-Download-SRA-Data)
- [3 Source](#3-Source)
- [4 Reference](#4-Reference)

***

***Author***\*\* : JZHANG\*\*​

***Date***\*\* : 2025-12-17\*\*​

***Version***\*\* : \*\***`1.1v`**

***

## 1 Introduce

### `1.1 AWS S3`

\*\*`Amazon Simple Storage Service（Amazon S3）`\*\*是一项对象存储服务，在可扩展性、数据可用性、安全性和能效方面业界领先。数百万不同规模和行业的客户可以为几乎任何应用场景存储、管理、分析和保护任意数量的数据，例如数据湖、云原生应用程序和移动应用程序。借助高成本效益的存储类和易于使用的管理功能，您可以优化成本、组织并分析数据，以及配置精细调整过的访问控制，从而满足特定的业务和合规性要求[^1]。

### `1.2 AWS S3` Features

**可扩展性** : 可以使用 `S3` 存储几乎任何数量的数据，一直到`EB`级，性能无与伦比。`S3` 具有完全的弹性，可以随着您增减数据的操作自动扩展和收缩。无需预置存储，只需按实际使用量付费。

**持久性 & 可用性** : `Amazon S3` 提供最持久的云端存储和业界领先的可用性。基于其独特的架构，`S3` 设计为默认提供 99.999999999%（11 个 9）的数据持久性和 99.99% 的可用性，并以云端最强的 `SLA` 为后盾。

\*\*安全性 \*\*: 通过无与伦比的安全性、数据保护、合规性和访问控制功能保护您的数据。`S3` 是安全、私有且默认加密的，还支持多种审计功能来监控对 `S3` 资源的访问请求。

**性价比** : `S3` 为任何工作负载和自动数据生命周期管理提供具有最佳性价比的多种存储类，因此您可以以经济高效的方式存储大量经常、不经常或很少访问的数据。`S3` 提供弹性、灵活性、延迟和吞吐量，确保存储永不限制性能。

## 2 Tutorial

### 2.1 AWS CLI

`aws s3 cli`是亚马逊云对象存储命令行工具[^2]。

#### 2.1.1 Install `aws cli`

```python title="安装最新版aws cli"
# 安装最新版 aws cli
curl "https://s3.amazonaws.com/aws-cli/awscli-bundle.zip" -o "awscli-bundle.zip"
unzip awscli-bundle.zip
sudo ./awscli-bundle/install -i /usr/local/aws -b /usr/local/bin/aws
```


#### 2.1.2 configure aws

```bash title="配置aws"
# 配置aws 根据同时输入配置信息
aws configure
AWS Access Key ID [None]: AKIAIOSFODNN7EXAMPLE
AWS Secret Access Key [None]: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
Default region name [None]: us-west-2
Default output format [None]: json

```


> **NOTE** : 使用`aws configure`命令设置的较不敏感的配置选项（如默认区域和输出格式）会被存储在主目录下的`.aws`文件夹中的`config`文件里。

> **Tips** : 除了可以使用`aws configure`设置配置信息外，还可以将相关配置添加到环境变量。
>
> ```bash title="aws环境变量"
> export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
> export AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
> export AWS_DEFAULT_REGION=us-west-2
> ```
>

#### 2.1.3 aws command

##### 2.1.3.1 Create bucket

使用[s3 mb](https://docs.aws.amazon.com/cli/latest/reference/s3/mb.html "s3 mb")命令创建存储桶。存储桶名称必须是全局唯一的（在所有 Amazon S3 存储桶中都是唯一的），并且应符合 DNS 标准。

> **NOTE** : 存储桶名称可以包含小写字母、数字、连字符和点号。存储桶名称只能以字母或数字开头和结尾，连字符或点号后不能跟点号。

```bash title="创建bucket"
# 创建 amzn-s3-demo-bucket bucket
aws s3 mb s3://amzn-s3-demo-bucket
```


##### 2.1.3.2 list bucket or object

要列出存储桶、文件夹或对象，请使用[s3 ls](https://docs.aws.amazon.com/cli/latest/reference/s3/ls.html "s3 ls")命令。使用不带目标或选项的命令时，将会列出所有存储桶。

```bash title="list bucket"
# 列出当前账号下所有bucket
aws s3 ls
# 列出amzn-s3-demo-bucket下所有对象
aws s3 ls s3://amzn-s3-demo-bucket
# 列出特定区域内的存储桶和对象
aws s3 ls --region us-east-2

```


##### 2.1.3.3 delete bucket

[s3 rb](https://docs.aws.amazon.com/cli/latest/reference/s3/rb.html "s3 rb")命令删除存储桶

```bash title="delete bucket"
# 删除 s3://amzn-s3-demo-bucket 存储桶# 
aws s3 rb s3://amzn-s3-demo-bucket
```


> **NOTE** : 默认情况下，存储桶必须为空，此操作才能成功。要删除不为空的存储桶，您必须包含`--force`选项。
>
> ```bash title="delete bucket"
> # 强制删除非空bucket
> aws s3 rb s3://amzn-s3-demo-bucket --force
> ```
>

##### 2.1.3.4 Delete object

[s3 rm](https://docs.aws.amazon.com/cli/latest/reference/s3/rm.html "s3 rm")命令删除存储桶或本地目录中的对象。

```bash title="Delete object"
# 删除filename.txt
aws s3 rm s3://amzn-s3-demo-bucket/example/filename.txt
```


##### 2.1.3.5 move object

[s3 mv](https://docs.aws.amazon.com/cli/latest/reference/s3/mv.html "s3 mv")命令可从存储桶或本地目录中移动对象。`s3 mv`命令将源对象或文件复制到指定目标，然后删除源对象或文件。

```bash title="move object"
# 将所有对象从 s3://amzn-s3-demo-bucket/example 移动到 s3://amzn-s3-demo-bucket/。
aws s3 mv s3://amzn-s3-demo-bucket/example \
       s3://amzn-s3-demo-bucket/
# 将本地文件从当前工作目录移动到 Amazon S3 存储桶。
aws s3 mv filename.txt s3://amzn-s3-demo-bucket
# 将文件从 Amazon S3 存储桶移动到当前工作目录
aws s3 mv s3://amzn-s3-demo-bucket/filename.txt ./

```


##### 2.1.3.6 copy object

[s3 cp](https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html "s3 cp") : 从存储桶或本地目录复制对象。

```bash title="copy object"
# 从 s3://amzn-s3-demo-bucket/example 复制到 s3://amzn-s3-demo-bucket/
aws s3 cp s3://amzn-s3-demo-bucket/example s3://amzn-s3-demo-bucket/
# 将本地文件从当前工作目录复制到 Amazon S3 存储桶
aws s3 cp filename.txt s3://amzn-s3-demo-bucket
# 从 Amazon S3 存储桶复制到当前工作目录
aws s3 cp s3://amzn-s3-demo-bucket/filename.txt ./
```


```bash title="aws s3 cp"
# 递归下载 IRGSP-1.0 bucket 中的所有文件
aws s3 cp --no-sign-request \
          --recursive \
          s3://ngi-igenomes/igenomes/Oryza_sativa_japonica/Ensembl/IRGSP-1.0/ ./
```


##### 2.1.3.7 sync object

[s3 sync](https://docs.aws.amazon.com/cli/latest/reference/s3/sync.html "s3 sync")命令同步一个存储桶与一个目录中的内容，或者同步两个存储桶中的内容。

```bash title="sync object"
aws s3 sync <source> <target> [--options]
```


### 2.2 Download SRA Data

下载海量 `SRA` 数据（特别是 `TB` 级的大项目）时，传统的 `HTTP/FTP` 协议经常会遇到速度慢、容易断连的问题。目前的**最优解**是：利用 `NCBI` 在`AWS` 上的 `Open Data (ODP)` 镜像，直接通过\*\*`S3`协议\*\* 进行传输。这种方式不仅无需账号（免密），而且速度极快且稳定,同时支持断点续传！。

> 👨🏼‍💻**SRA Data & AWS操作步骤：**
>
> 1. **确认来源**：在 `SRA Run Selector` 中确认你的目标数据（如`SRR32730731`）是否托管在 `AWS` 存储桶中。
>
>    ![](image/image_I2kE0uyyM6.png)
> 2. **预览检查**：下载前推荐先用`ls` 命令看一下远端的文件结构和大小，做到心里有数。
>
>    ![](image/image_r9J_toEOiV.png)
> 3. **执行下载**：使用`cp`命令传输。关键是加上`--no-sign-request`参数，这是**免密下载**的核心。(PS: 为了加速下载可以同时运行多个下载命令)
>
>    ![](image/image_wCAbj67pIv.png)
> 4. **性能调优 (关键)**：默认配置可能跑不满你的带宽，建议调整 `AWS CLI` 的并发和分片参数（见下方代码），下载速度会有质的飞跃。
>    ```markdown title="aws configure"
>    # 1. 设置最大并发请求数 (默认只有10，改成20或50试试)
>    aws configure set default.s3.max_concurrent_requests 20
>    # 2. 设置分片大小 (大文件分片下载更快)
>    aws configure set default.s3.multipart_chunksize 16MB
>    # 3. 设置队列大小
>    aws configure set default.s3.max_queue_size 10000
>    ```
>

***

## 3 Source

> `amazon` 云上托管了不少已经建好的index,可以免费下载
>
> [ Index zone by BenLangmead  https://benlangmead.github.io/aws-indexes/](https://benlangmead.github.io/aws-indexes/ " Index zone by BenLangmead  https://benlangmead.github.io/aws-indexes/")

> **在 AWS CLI 中使用高级（s3）命令**
>
> [ 在 AWS CLI 中使用高级（s3）命令 - AWS Command Line Interface 通过 AWS CLI 在 aws s3 命名空间中使用高级别 Amazon S3 命令管理桶和对象。 https://docs.aws.amazon.com/zh\_cn/cli/v1/userguide/cli-services-s3-commands.html](https://docs.aws.amazon.com/zh_cn/cli/v1/userguide/cli-services-s3-commands.html " 在 AWS CLI 中使用高级（s3）命令 - AWS Command Line Interface 通过 AWS CLI 在 aws s3 命名空间中使用高级别 Amazon S3 命令管理桶和对象。 https://docs.aws.amazon.com/zh_cn/cli/v1/userguide/cli-services-s3-commands.html")

## 4 Reference

[^1]: [https://aws.amazon.com/cn/s3/?nc=sn\&loc=0](https://aws.amazon.com/cn/s3/?nc=sn\&loc=0 "https://aws.amazon.com/cn/s3/?nc=sn\&loc=0")

[^2]: [https://docs.aws.amazon.com/cli/latest/reference/s3/](https://docs.aws.amazon.com/cli/latest/reference/s3/ "https://docs.aws.amazon.com/cli/latest/reference/s3/")
