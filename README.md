# Wlab-antiSMASH

本仓库保存了本实验室所用过的antiSMASH版本的源代码，提供了安装指南便于安装使用。

仓库内存放多个版本的antiSMASH包，每个版本的文件夹中主要包含两个子文件夹（1. 命令文件夹bin 2.antismash包），将这两个子文件夹以及数据库文件（3. databases）放置合适的路径，即可手动安装成功。

额外的python包等工具需自行利用 `pip` 或 `conda` 手动安装。



以下安装步骤以antiSMASH_5.2.0为例，其他版本的安装只需替换命令中相应的版本号即可。

## 0. 创建环境

创建环境

```bash
conda create -n antismash_5.2.0 python=3.8  # 创建环境
conda activate antismash_5.2.0  #激活环境
```

此时生成了两个后续会放置文件的路径：

- `~/miniconda3/envs/antismash_5.2.0/bin/` 

- `~/miniconda3/envs/antismash_5.2.0/lib/python3.8/site-packages/`



## 1. 命令脚本文件

命令脚本文件 `bin`

将本仓库中 `antismash_5.2.0/bin` 文件夹中的两个脚本文件（Unix可执行文件）放置到 `~/miniconda3/envs/antismash_5.2.0/bin/` 目录下

```bash
cp antismash_5.2.0/bin/* ~/miniconda3/envs/antismash_5.2.0/bin/
```



## 2. antismash 包

选择一个目标版本进行安装，本仓库目前提供了如下几个版本，如需其他版本，请至 [antismash 仓库](https://github.com/antismash/antismash) 查看。（不同版本的antiSMASH需要不同的数据库）

- antiSMASH 5.2.0

- antiSMASH 6.0.1

- antiSMASH 7.0.1

将目标版本5.2.0的 antismash 包文件放置到 `~/miniconda3/envs/antismash_5.2.0/lib/python3.8/site-packages/` 目录下

```bash
cp -r antismash_5.2.0/antismash ~/miniconda3/envs/antismash_5.2.0/lib/python3.8/site-packages/
```



## 3. databases

由于国内利用官方提供的下载命令下载数据库十分困难，这里将数据库保存到百度网盘供大家下载。

不同版本的 antiSMASH 需要不同的数据库，请自行下载对应版本的数据库。

- antiSMASH 5.2.0 databases

链接: https://pan.baidu.com/s/1I10MHi8uml7tdRj9vVcUDQ?pwd=iimw 提取码: iimw 

- antiSMASH 6.0.1 databases

链接: https://pan.baidu.com/s/135QqIilkOun9X3o6ia1uzg?pwd=ow0h 提取码: ow0h 

- antiSMASH 7.0.1 databases

链接: https://pan.baidu.com/s/121MZ2clT4BVuMkDR2Qsllw?pwd=v72a 提取码: v72a



将下载的数据库文件放置到 antismash 包文件夹下的 `databases` 文件夹中

```
unzip antismash_databases_5.2.0.zip
cp -r antismash_5.2.0_databases/* ~/miniconda3/envs/antismash_5.2.0/lib/python3.8/site-packages/antismash/databases
```



## 4. 环境构建

利用 `conda` 构建运行环境，一下提供两种构建方式，选择其一即可（此处构建教程可能并不完整，具体环境要求可根据相关报错解决）

### 4.1 根据环境配置文件安装

```bash
conda env update --file antismash_5.2.0/antismash.yaml
pip install -r antismash_5.2.0/requirements.txt
```

### 4.2 手动一步步安装

```bash
conda install hmmer2 hmmer diamond fasttree prodigal blast glimmerhmm
conda install muscle=3.8.1551  # 安装5.1版本会报错
```

```bash
pip install biopython helperlibs bcbio-gff jsonschema pysvg-py3 joblib scikit-learn matplotlib pyscss
conda install jinja2=3.0.3
```

如果要使用 CASSIS 分析，需要安装 meme (⚠️CASSIS cluster prediction only works for fungal sequence.)

```bash
conda install meme=4.11.2
```



## 5. 校验与使用

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

