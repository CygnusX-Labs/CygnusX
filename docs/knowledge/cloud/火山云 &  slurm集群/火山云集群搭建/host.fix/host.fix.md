# `host.fix`

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 Scripts require](#11-Scripts-require)
  - [1.2 host.fix.py](#12-hostfixpy)
  - [1.3 host.fix.sh](#13-hostfixsh)
  - [1.4 add server](#14-add-server)
  - [1.5 run hosts.fix server](#15-run-hostsfix-server)
- [2 Scripts](#2-Scripts)

## 1 Introduce

由于火山云`slurm`集群hosts文件无法进行实时更新，因此基于火山云 `SDK` & `API` 使用python编写了自动更新`/etc/hosts`文件脚本。为了保证任务可以实时运行，因此将相关脚本封装为`server`服务。

> NOTE:由于替换`hosts`需要较高权限，因此需要在`root`账号下进行操作

### 1.1 Scripts require

> NOTE: `host.fix.py` 需要在python3环境下运行。

```python 
# install volcengine python sdk
pip install volcengine-python-sdk
# python require
pip install pandas
pip install numpy
pip install calendra
```


### `1.2 host.fix.py`

`host.fix.py` 脚本是使用`volcengine-python-sdk`对当前账号下的`slurm`集群的计算节点IP进行拉取并按照hosts格式整理为`update.hosts`文件。

> NOTE:由于需要拉取特定账号下的slurm信息，因此需要提供对应KEY & Cluster ID等信息。

```yaml 
# Slurm info
REGION : "cn-shanghai"
AKS:
  AK : "xxxxxxxxxxxx"
  AKS : "xxxxxxxxxxxx"
CLUSTER_ID : '10180'
MASTER_INFOR : "10.160.25.13 scheduler\n"
PATTERN : r'vector-\d+-cpu-\d+-[a-f0-9-]+-\d+'
# Scripts folder
PATH_FIX_HOSTS : '/root/hosts_fix'
```


```yaml 
# 如果火山云slurm集群为高可用集群则需要将MASTER_INFOR修改为对应内容，示例如下
# Slurm info
REGION : "cn-shanghai"
AKS:
  AK : "xxxxxxxxxxxxxxxx"
  AKS : "xxxxxxxxxxxxxxxxx"
CLUSTER_ID : '10180'
MASTER_INFOR : "10.160.25.13 scheduler\n10.160.25.15 login-0\n10.160.25.16 login-1\n10.160.25.14 scheduler-ha\n"
PATTERN : r'vector-\d+-cpu-\d+-[a-f0-9-]+-\d+'
# Scripts folder
PATH_FIX_HOSTS : '/root/hosts_fix'
```


```bash 
<python3-path> <PATH>/host.fix.py
```


### `1.3 host.fix.sh`

由于Ubantu的server服务无法使用python脚本，同时也为了保证可以替换`/etc/hosts`文件，因此将`host.fix.py`脚本与`/etc/hosts`替换封装为`bash`脚本。

```bash 
#!/bin/bash
# 运行 `host.fix.py` 脚本
<python3-PATH> <PATH>/host.fix.py
# 替换hosts文件
sudo cp <PATH>/update.hosts /etc/hosts
```


### 1.4 add server

`host.fix.service` 为hosts.fix脚本服务service脚本,在使用时需要将`host.fix.service`放到`/etc/systemd/system/`目录中。

```bash 
# host.fix.service 脚本内容如下
[Unit]
Description=Host Fix Script
[Service]
Type=oneshot
ExecStart=<PATH>/host.fix.sh
```


`host.fix.timer`脚本为设定的服务运行设置，可以设置运行数据(ps:可以设定运行的时间)。该文件也需要放到`/etc/systemd/system/`目录中。

```bash 
# `host.fix.timer`服务内容如下:
#  每10秒运行一下server
[Unit]
Description=Run Host Fix Script every 10 seconds
[Timer]
OnBootSec=10
OnUnitActiveSec=10
[Install]
WantedBy=timers.target
```


### 1.5 run hosts.fix server

准备好以上内容后就安装下面的命令运行hosts.fix server

```bash 
sudo systemctl daemon-reload
sudo systemctl enable host.fix.timer
sudo systemctl start host.fix.timer
```


使用`systemctl status host.fix`命令查看`host.fix`服务状态,如果为`activating`,表明服务已经正常运行啦。

```bash 
# 使用systemctl status命令查看host.fix服务状态
sudo systemctl status host.fix
● host.fix.service - Host Fix Script
     Loaded: loaded (/etc/systemd/system/host.fix.service; static)
     Active: activating (start) since Tue 2025-01-14 17:07:49 CST; 4ms ago
TriggeredBy: ● host.fix.timer
   Main PID: 4102086 (host.fix.sh)
      Tasks: 2 (limit: 38372)
     Memory: 988.0K
        CPU: 1ms
     CGroup: /system.slice/host.fix.service
             ├─4102086 /bin/bash /root/hosts_fix/host.fix.sh
             └─4102088 /opt/vector/system/embedded/bin/python3 /root/hosts_fix/host.fix.py
```


## 2 Scripts

> 修复`hosts`文件脚本：
>
> [host.fix.yaml](file/host.fix_ZpYNlElPNZ.yaml "host.fix.yaml")
>
> [host.fix.service](file/host.fix_oCwUoafimA.service "host.fix.service")
>
> [host.fix.sh](file/host.fix_esRnfB0gpb.sh "host.fix.sh")
>
> [host.fix.timer](file/host.fix_GU--AwuWz5.timer "host.fix.timer")
>
> [host.fix.py](file/host.fix_eb56KiiBGU.py "host.fix.py")
