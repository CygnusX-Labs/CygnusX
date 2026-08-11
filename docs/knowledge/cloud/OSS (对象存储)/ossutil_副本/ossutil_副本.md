# ossutil\_副本

## 目录

- [1 Introduce](#1-Introduce)
- [2 Install](#2-Install)
- [3 tutorial](#3-tutorial)
  - [3.1 general command](#31-general-command)
  - [3.2 Python api](#32-Python-api)
- [4 Reference](#4-Reference)

## 1 Introduce

ossutil支持通过Windows、Linux和macOS系统以命令行方式管理OSS[^1]数据。

## 2 Install

```bash 
# download & install & test
wget https://gosspublic.alicdn.com/ossutil/1.7.19/ossutil-v1.7.19-linux-amd64.zip
unzip ossutil-v1.7.19-linux-amd64.zip
cd ossutil-v1.7.19-linux-amd64
./ossutil -v
ossutil version: v1.7.19

```


## 3 tutorial

### 3.1 general command

```bash 
# cp（上传、下载和拷贝文件）
# create-symlink（创建软链接）
# du（获取大小）
# mb（创建存储空间）
# mkdir（创建目录）
# rm（删除）
```


```r 
# add endpoint infor
-e, --endpoint          # 请求的域名
ossutil64 commandname options -e oss-cn-hangzhou.aliyuncs.com
# add key ID
-i, --access-key-id     # 访问OSS使用的访问凭证
ossutil64 commandname options -i your_access_key
# add secret
-k, --access-key-secret # 访问OSS使用的访问凭证
ossutil64 commandname options -k your_access_key_secrect


```


> aliyuncs ： endpoint地址

[ OSS访问域名和数据中心\_对象存储(OSS)-阿里云帮助中心 Region表示OSS的数据中心所在的地域，Endpoint表示OSS对外服务的访问域名。本文主要介绍Region与Endpoint的对应关系。 https://help.aliyun.com/zh/oss/user-guide/regions-and-endpoints](https://help.aliyun.com/zh/oss/user-guide/regions-and-endpoints " OSS访问域名和数据中心_对象存储(OSS)-阿里云帮助中心 Region表示OSS的数据中心所在的地域，Endpoint表示OSS对外服务的访问域名。本文主要介绍Region与Endpoint的对应关系。 https://help.aliyun.com/zh/oss/user-guide/regions-and-endpoints")

### 3.2 Python api

> 阿里云OSS访问除了可以使用ossutil，还可以使用oss2的api!

[ 阿里云OSS Python SDK — oss2  文档  https://gosspublic.alicdn.com/sdks/python/apidocs/latest/zh-cn/index.html](https://gosspublic.alicdn.com/sdks/python/apidocs/latest/zh-cn/index.html " 阿里云OSS Python SDK — oss2  文档  https://gosspublic.alicdn.com/sdks/python/apidocs/latest/zh-cn/index.html")

## 4 Reference

[ 命令行工具ossutil\_对象存储(OSS)-阿里云帮助中心  https://help.aliyun.com/zh/oss/developer-reference/ossutil-1/?spm=a2c4g.11186623.0.0.7839508fm3bD2e](https://help.aliyun.com/zh/oss/developer-reference/ossutil-1/?spm=a2c4g.11186623.0.0.7839508fm3bD2e " 命令行工具ossutil_对象存储(OSS)-阿里云帮助中心  https://help.aliyun.com/zh/oss/developer-reference/ossutil-1/?spm=a2c4g.11186623.0.0.7839508fm3bD2e")

[^1]: Object Storage Service 对象存储
