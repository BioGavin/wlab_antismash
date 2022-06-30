# Wlab-antiSMASH

本仓库保存了本实验室所用过的antiSMASH版本的源代码，提供了安装指南便于安装使用。

仓库内主要包含两个文件夹，将两个文件夹（1.命令脚本文件 2. antismash 包）以及数据库文件（3. databases）放置合适的路径，即可手动安装成功。

额外的python包等工具需自行利用 `pip` 或 `conda` 手动安装。



## 0. 创建环境

创建环境

```bash
conda create -n antismash python
```

此时生成了两个后续会放置文件的路径：

- `~/miniconda3/envs/antismash/bin/` 

- `~/miniconda3/envs/antismash/lib/python3.10/site-packages/`



## 1. 命令脚本文件

命令脚本文件 `scripts`

将本仓库中 `scripts` 文件夹中的两个脚本文件（Unix可执行文件）放置到 `~/miniconda3/envs/antismash/bin/` 目录下

```bash
cp scripts/* ~/miniconda3/envs/antismash/bin/
```



## 2. antismash 包

选择一个目标版本进行安装，本仓库目前提供了如下几个版本，如需其他版本，请至 [antismash 仓库](https://github.com/antismash/antismash) 查看。（不同版本的antiSMASH需要不同的数据库）

- antiSMASH 5.2.0

- antiSMASH 6.0.1

将目标版本的 antismash 包文件放置到 `~/miniconda3/envs/antismash/lib/python3.10/site-packages/` 目录下

```bash
cp antismash_x.x.x ~/miniconda3/envs/antismash/lib/python3.10/site-packages/antismash  # 将 x.x.x 改为你的目标版本号
```



## 3. databases

由于国内利用官方提供的下载命令下载数据库十分困难，这里将数据库保存到百度网盘供大家下载。

不同版本的 antiSMASH 需要不同的数据库，请自行下载对应版本的数据库。

- antiSMASH 5.2.0 databases

链接: https://pan.baidu.com/s/1I10MHi8uml7tdRj9vVcUDQ?pwd=iimw 提取码: iimw 

- antiSMASH 6.0.1 databases

链接: https://pan.baidu.com/s/135QqIilkOun9X3o6ia1uzg?pwd=ow0h 提取码: ow0h 



将下载的数据库文件放置到 antismash 包文件夹下的 `databases` 文件夹中

```
cp -r antismash_x.x.x_database/* ~/miniconda3/envs/antismash/lib/python3.10/site-packages/antismash/databases
```



## 4. 校验与使用

1. 数据库的校验，运行以下命令，如果显示数据库准备完成即可

```bash
download-antismash-databases
```

2. 使用与帮助

```bash
antismash -h  # 查看帮助
antismash --version  # 查看版本
```



## 其他问题

如有其他问题可[邮件](mailto:gavinchou99@126.com)与我联系。

