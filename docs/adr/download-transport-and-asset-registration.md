# ADR：复用下载传输器、统一登记与独立来源认证

状态：S1登记与S2来源契约已实现；运行发布未准入。日期：2026-10-16。

## 背景

平台下载子模块EBIDownload1.4.0、宿主历史观察1.4.0、旁仓Polariseq1.4.3不同。Python Worker镜像没有构建Rust下载器，二进制来自运维数据盘路径；仅改Python源码或Compose tag无法证明实际Worker版本。原下载登记绕过统一FileRegistry，已在S1修复。

## 决定

1. 继续复用DownloadService/既有Task/Worker和EBIDownload、aria2c、三家CLI；FileRecord继续由已有FileRegistry写入真实Task/source/实测SHA。没有第二套下载器、文件表或队列。
2. S2保留当前外置工具部署方式，不自动重编/升级/复制Polariseq，不修改Worker镜像或宿主程序。本阶段建立可复核清单，而不是把未知版本打包成“已验收镜像”。
3. 若后续继续选择共享盘程序模式，必须为实际Worker记录不可变镜像digest、UID/GID、程序及依赖version/hash/help与只读binary挂载；数据目录仍可写。当前Compose共享盘不等于binary只读，清单会标未验证。真正增加只读挂载或打包程序须另轮部署授权；若改为镜像内打包，需固定版本与下载checksum/源码commit、记录Rust工具链/Cargo.lock并遵守仓库镜像规范。
4. 协议声明单一化：平台SRA仅aws/ftp；CLI prefetch/auto暂不开放，Aspera不静默映射。普通直链仅http/https/匿名ftp，配置只能收紧集合；云盘、FTPS、通用S3/COS保持未实现。来源解析不等于网络传输认证。
5. 运维manifest是离线核对工具，不是运行Gate授权服务。来源/观察一致也不释放execute；保持Agent写门禁与Handoff路径门禁。

## 后果与回滚

人工三类表单继续保留，失真或未接线选项不再假装生效。已有排队的Aspera任务会明确失败，不能重映射成FTP；其文件/Task保留对账。显式YAML路径仍优先，env二进制路径在YAML缺省时才生效。

S1回滚保留所有文件/Task/登记记录，仅按本轮hunk还原代码。S2可按阶段基线撤回协议/展示与离线工具，但不能把虚假Aspera/云盘宣传当作安全回滚方案。无需数据库迁移，不自动部署或开启开关。当前工作区存在另行新增的下载安全/能力接口修改，须由其修改方独立验证并说明人工入口行为；本ADR不为它们背书。
