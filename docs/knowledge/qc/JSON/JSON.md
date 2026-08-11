# `JSON`

## 目录

- [1 Introduce](#1-Introduce)
  - [1.1 JSON](#11-JSON)
    - [JSON Base Datatypes](#JSON-Base-Datatypes)
    - [JSON: Advanced & Limited](#JSON-Advanced--Limited)
    - [1.1.3 JSON Data Stucture](#113-JSON-Data-Stucture)
- [2 Tutorial](#2-Tutorial)
  - [2.1 Python](#21-Python)
- [3 Reference](#3-Reference)

***

***Author***\*\* : zhang jian\*\*​

***Date***\*\* : 2025-4-16\*\*​

***Version***\*\* : \*\***`1.0v`**

***

## 1 Introduce

### `1.1 JSON`

`JSON`（`JavaScript Object Notation`,`JavaScript`对象表示法）是由美国程序员道格拉斯·克罗克福特构想和设计的一种轻量级资料交换格式[^1][^2]。其内容由属性和值所组成，因此也有**易于阅读和处理**的优势。`JSON`是独立于编程语言的资料格式，其不仅是`JavaScript`的子集，也采用了`C`语言家族的习惯用法，目前也有许多编程语言都能够将其解析和字符串化，其广泛使用的程度也使其成为通用的资料格式。

`JSON`类似 `XML`,但`JSON` 比 `XML` 更小、更快，更易解析，易于人阅读和编写。`C`、`Python`、`C++`、`Java`、`PHP`、`Go` 等编程语言都支持 `JSON`。

#### **`JSON`** Base Datatypes

> 🍖\*\*`JSON`\*\***支持的基本数据类型**
>
> - **数值**：十进制数，不能有前导0，可以为负数，可以有小数部分。还可以用`e`或者`E`表示指数部分。不能包含非数，如`NaN`。不区分整数与浮点数。`JavaScript`用双精度浮点数表示所有数值（后来也支持 BigInt）[^3]。
> - **字符串**：以双引号`""`括起来的零个或多个Unicode[码位](https://zh.wikipedia.org/wiki/码位 "码位")。支持反斜杠开始的转义字符序列。
> - **布尔值**：表示为`true`或者`false`。
> - **数组**：有序的零个或者多个值。每个值可以为任意类型。数组使用方括号`**[]**`包裹。多个数组元素之间用逗号`**,**`分隔，形如：`[value, value]`。
> - **对象**：若干无序的**键-值对(key-value pairs)**，其中键只能是字符串。建议但不强制要求对象中的键是独一无二的。对象以花括号`{}`包裹。多个键-值对之间使用逗号`,`分隔。键与值之间用冒号`:`分隔。
> - **空值**：值写为`null`

#### **JSON: Advanced & Limited**

> 🎱**JSON: Advanced & Limited**
>
> > **Advanced**
> >
> > 1. **与 JavaScript 完美兼容**：JSON 格式源自 JavaScript，因此它与 JavaScript 非常兼容，并且易于在 JavaScript 应用程序中使用。
> > 2. **轻量级**：JSON 格式非常轻量级，因此它非常适合在网络中传输大量数据。相比于 XML，它的数据量更小，传输速度更快。
> > 3. **多语言支持**：JSON 格式是一种跨语言的格式，它可以被许多不同语言的程序支持，易于解析和生成，几乎所有编程语言都支持 JSON。
> > 4. **易于阅读和编辑**：JSON 格式非常易于阅读和编写，因为它具有简单的语法和结构，格式清晰，具有良好的可读性。
>
> > **Limited**
> >
> > 1. **不支持注释：** JSON 格式不支持注释，这可能使得编写和维护复杂数据时变得有些困难。
> > 2. **无法表示二进制数据：** JSON 格式无法直接表示二进制数据，这意味着它无法用于存储和传输图像、视频等二进制数据。
> > 3. **不支持命名空间：** JSON 不支持命名空间，这可能会导致不同的应用程序之间发生命名冲突。
> > 4. **不支持DTD：** JSON 不支持 DTD，这使得在验证 JSON 数据格式时不太方便。

> **`XML`**\*\* vs \*\***`JSON`**
>
> | \`\`\`xml title="xml " {   "title": "Harry Potter",   "author": "J.K. Rowling",   "year": 2005 } \`\`\` | \`\`\`json title="json" {   "title": "Harry Potter",   "author": "J.K. Rowling",   "year": 2005 } \`\`\` |
> | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |

#### `1.1.3 JSON` Data Stucture

`JSON` 由两种数据结构组成：**对象**和**数组**。

**对象（object）** 是由键值对组成的无序集合，键是字符串，值可以是任何类型，包括对象和数组。对象由一对花括号`{ }`包围，键和值之间用冒号`:`分隔。键值对之间用逗号`,`分隔

```json title="JSON Object"
# JSON 对象示例
{
    "list" : [ 
        {
            "name": "zj",
            "ID": '007',
            "city": "Earth"
        }
    ] 
}
```


**数组（array）** 是值（value）的有序集合，每个值可以是任何类型，包括对象和数组。数组由一对方括号`[ ]`包裹，值之间用逗号`,`分隔。

```json title="JSON Array"
# JSON 数组示例
[  "apple",  "banana",  "orange"]
```


**值（value）** 可以是花括号`{ }`括起来的字符串（String）、数值(Number)、布尔值(true/false)、 null、对象（Object）或者数组（Array），这些结构可以嵌套。

```json title="JSON value"
# 字符串 : JSON 字符串是由双引号" "包围的 Unicode 字符序列，使用反斜杠 `` 转义
{
  "name": "Apifox",
  "city": "Guangzhou"
}
# 数字 : JSON 数字可以是整数或浮点数
{
  "age": 30,
  "weight": 65.5
}
# 布尔值 : JSON 布尔值只有两个取值：true 和 false
{
  "isStudent": true,
  "isEmployed": false
}
# null : JSON 的 null 表示一个空值
{
  "middleName": null
}
```


> 🎱**NOTE : 注意事项**
>
> - `JSON`的字符串必须使用双引号`" "`，而不能使用单引号`' '`。
> - `JSON`的值可以是字符串、数字、布尔值、null、对象或数组。
> - `JSON`的键必须是字符串，必须使用双引号`" "`。
> - `JSON`的格式必须严格遵守规定，否则可能会导致解析错误。

***

## 2 Tutorial

### 2.1 Python

```r title="import json → dict"
import json
# loading json -> dict
with open(i,'r') as load_f:
            load_dict = json.load(load_f)

```


***

## 3 Reference

[^1]: [https://zh.wikipedia.org/wiki/JSON](https://zh.wikipedia.org/wiki/JSON "https://zh.wikipedia.org/wiki/JSON")

[^2]: [https://zh.wikipedia.org/wiki/%E9%81%93%E6%A0%BC%E6%8B%89%E6%96%AF%C2%B7%E5%85%8B%E7%BE%85%E5%85%8B%E7%A6%8F%E7%89%B9](https://zh.wikipedia.org/wiki/%E9%81%93%E6%A0%BC%E6%8B%89%E6%96%AF%C2%B7%E5%85%8B%E7%BE%85%E5%85%8B%E7%A6%8F%E7%89%B9 "https://zh.wikipedia.org/wiki/%E9%81%93%E6%A0%BC%E6%8B%89%E6%96%AF%C2%B7%E5%85%8B%E7%BE%85%E5%85%8B%E7%A6%8F%E7%89%B9")

[^3]: [https://developer.mozilla.org/en-US/docs/Glossary/BigInt](https://developer.mozilla.org/en-US/docs/Glossary/BigInt "https://developer.mozilla.org/en-US/docs/Glossary/BigInt")
