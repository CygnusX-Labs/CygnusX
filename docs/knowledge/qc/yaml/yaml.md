# yaml

## 目录

- [1 introduce](#1-introduce)
  - [1.1 YAML](#11-YAML)
  - [1.2 feature](#12-feature)
  - [1.3 basic elements](#13-basic-elements)
- [2 tutorial](#2-tutorial)
  - [2.1 YAML](#21-YAML)
  - [2.2 python & YAML](#22-python--YAML)
  - [2.3 R & YAML](#23-R--YAML)
- [3 Source](#3-Source)
- [4 reference](#4-reference)

***

## 1 introduce

### 1.1 YAML

> YAML（`/ˈjæməl/`）是一个可读性高，用来表达**数据序列化**的格式。YAML参考了其他多种语言，包括：C语言、Python、Perl，并从XML、电子邮件的数据格式（RFC 2822）中获得灵感。**Clark Evans**在2001年首次发表了这种语言，另外**Ingy döt Net**与**Oren Ben-Kiki**也是这语言的共同设计者。目前已经有数种编程语言或脚本语言支持（或者说解析）这种语言[^1]。

> YAML是"**YAML Ain't a Markup Language**"（YAML不是一种标记语言）的递归缩写。在开发的这种语言时，YAML的意思其实是："**Yet Another Markup Language**"（仍是一种标记语言），但为了强调这种语言以数据为中心，而不是以标记语言为重点，而用反向缩略语重命名[^2] 。

### 1.2 feature

> YAML的语法和其他高级语言类似，并且可以简单表达清单、散列表，标量等数据形态。它使用空白符号缩进和**大量依赖外观**的特色，特别适合用来表达或编辑数据结构、各种配置文件、倾印调试内容、文件大纲（例如：许多电子邮件标题格式和YAML非常接近）。尽管它比较适合用来表达层次结构式（hierarchical model）的数据结构，不过也有精致的语法可以表示关系性（relational model）的数据。由于YAML使用空白字符和分行来分隔数据，使得它特别适合用`grep／Python／Perl／Ruby`操作。其让人最容易上手的特色是巧妙避开各种封闭符号，如：引号、各种括号等，这些符号在嵌套结构时会变得复杂而难以辨认。

> **NOTE** : ***YAML 的配置文件后缀为 .yml***

### 1.3 basic elements

> **YAML**基础语法：
>
> - **大小写敏感**;
> - **使用****缩进****表示层级关系**;
> - 缩进不允许使用tab，只允许空格;
> - 缩进的空格数不重要，只要相同层级的元素左对齐即可;
> - `#`表示注释.

> **YAML 支持以下几种数据类型：**
>
> - **对象**：键值对的集合，又称为映射（**mapping**）/ 哈希（**hashes**） / 字典（**dictionary**）；
> - 数组：一组按次序排列的值，又称为序列（**sequence**） / 列表（**list**）；
> - 纯量（**scalars**）：单个的、不可再分的值。

***

## 2 tutorial

### 2.1 YAML

- \*\*YAML Object \*\*:&#x20;

  对象键值对使用冒号结构表示 `key: value`，冒号后面要加一个空格
  ```bash title="YAML Object "
  key: 
      key1: value
      key2: value2
      keyx: valuex
  ```

  **上面的YAML 等同于**`key:{key1: value1, key2: value2, ...}`
- **YAML Array**：

  以`-` 开头的行表示构成一个数组：
  ```bash title="YAML Array"
  - A
  - B
  - C
  ```


> 下面的yaml意思是 **`companies`** 属性是一个数组，每一个数组元素又是由\*\* ****`id`****、****`name`****、`price`\*\*三个属性构成
>
> ```bash title="Array + Object"
> companies:
>     -
>         id: 1
>         name: company1
>         price: 200W
>     -
>         id: 2
>         name: company2
>         price: 500W
> ```
>

- 纯量
  ```bash 
  boolean: 
      - TRUE  #true,True都可以
      - FALSE  #false，False都可以
  float:
      - 3.14
      - 6.8523015e+5  #可以使用科学计数法
  int:
      - 123
      - 0b1010_0111_0100_1010_1110    #二进制表示
  null:
      nodeName: 'node'
      parent: ~  #使用~表示null
  string:
      - 哈哈
      - 'Hello world'  #可以使用双引号或者单引号包裹特殊字符
      - newline
        newline2    #字符串可以拆成多行，每一行会被转化成一个空格
  date:
      - 2018-02-17    #日期必须使用ISO 8601格式，即yyyy-MM-dd
  datetime: 
      -  2018-02-17T15:02:31+08:00    #时间使用ISO 8601格式，时间和日期之间使用T连接，最后使用+代表时区
  ```

  字符串 & 布尔值 & 整数 & 浮点数 & Null & 时间 & 日期
- 引用

  `& `锚点和`  *  `别名，可以用来引用

  **`&`** 用来建立锚点（defaults），**`<<`**` `表示合并到当前数据，`* `用来引用锚点
  ```bash title="引用"
  defaults: &defaults
    adapter:  postgres
    host:     localhost

  development:
    database: myapp_development
    <<: *defaults

  test:
    database: myapp_test
    <<: *defaults
  ```

  ```bash title="引用"
  defaults:
    adapter:  postgres
    host:     localhost

  development:
    database: myapp_development
    adapter:  postgres
    host:     localhost

  test:
    database: myapp_test
    adapter:  postgres
    host:     localhost
  ```


### 2.2 python & YAML

[TEST.yaml](file/TEST_a27aZnCf3U.yaml "TEST.yaml")

```bash title="使用 python pyyaml 读取yaml文件"
# 使用 python pyyaml 读取yaml文件
# loading model
import yaml
# define model
def loading_yaml(yaml_dir):
    with open(yaml_dir, 'r') as file:
        prime_service = yaml.safe_load(file)
    return prime_service
# loading UNIVERscRNAseq.yaml
yaml_dir = "/home/zj/zj_vscode/UNIVERscRNAseq.yaml"
prime_service = loading_yaml(yaml_dir)
```


[PyYAML (yaml)](https://www.wolai.com/kyYRLb3C9Ki3RXUzHvRjXX "PyYAML (yaml)")

```bash title="YAML"
{'software': {'conda': '/home/zj/miniconda3/bin/activate',
  'qc': '/home/zj/miniconda3/envs/download'},
 'companies': [{'id': 1, 'name': 'company1', 'price': '200W'},
  {'id': 2, 'name': 'company2', 'price': '500W'}],
 'LIST': ['A', 'B', 'C'],
 'boolean': [True, False],
 'float': [3.14, 685230.15],
 'int': [123, 685230],
 None: {'nodeName': 'node', 'parent': None},
 'string': ['哈哈', 'Hello world', 'newline newline2'],
 'date': [datetime.date(2018, 2, 17)],
 'datetime': [datetime.datetime(2018, 2, 17, 15, 2, 31, tzinfo=datetime.timezone(datetime.timedelta(seconds=28800)))]}
```


### 2.3 R & YAML

```bash title="R yaml packages"
library('yaml')yaml_dir <- '/Users/zhangjian/Desktop/TEST.yaml'yaml.load_file(yaml_dir,readLines.warn = T)
```


```bash title="TEST.yaml"
$software$software$conda[1] "/home/zj/miniconda3/bin/activate"$software$qc[1] "/home/zj/miniconda3/envs/download"$companies$companies[[1]]$companies[[1]]$id[1] 1$companies[[1]]$name[1] "company1"$companies[[1]]$price[1] "200W"$companies[[2]]$companies[[2]]$id[1] 2$companies[[2]]$name[1] "company2"$companies[[2]]$price[1] "500W"$LIST[1] "A" "B" "C"$boolean[1]  TRUE FALSE$float[1]      3.14 685230.15$int$int[[1]][1] 123$int[[2]][1] "0b1010_0111_0100_1010_1110"[[7]][[7]]$nodeName[1] "node"[[7]]$parentNULL$string[1] "哈哈"             "Hello world"     [3] "newline newline2"$date[1] "2018-02-17"$datetime[1] "2018-02-17T15:02:31+08:00"
```


***

## 3 Source

[ YAML Tutorial : A Complete Language Guide with Examples Learn how to use YAML, one of the most popular data serialization languages that finds its uses almost everywhere where writing configuration is required.  https://spacelift.io/blog/yaml](https://spacelift.io/blog/yaml " YAML Tutorial : A Complete Language Guide with Examples Learn how to use YAML, one of the most popular data serialization languages that finds its uses almost everywhere where writing configuration is required.  https://spacelift.io/blog/yaml")

***

## 4 reference

[^1]: [https://en.wikipedia.org/wiki/YAML](https://en.wikipedia.org/wiki/YAML "https://en.wikipedia.org/wiki/YAML")

[^2]: [https://yaml.org/](https://yaml.org/ "https://yaml.org/")
