# md5sum

`md5sum` 是一个在 Unix 和类 Unix 系统中常用的命令行工具，用于计算和校验文件的 MD5（Message-Digest Algorithm 5）哈希值[^1]。

> 以下是 `md5sum` 的一些基本使用方法：

> **计算文件的 MD5 哈希值**
>
> ```markdown title="计算文件的 MD5 哈希值"
> # 计算单个文件的 MD5 哈希值
> md5sum filename
> # 计算多个文件的 MD5 哈希值
> md5sum file1 file2 file3
> # 计算目录下所有文件的 MD5 哈希值
> md5sum /path/to/directory/*
>
> ```
>

> **校验文件的 MD5 哈希值**
>
> ```markdown title="校验文件的 MD5 哈希值"
> # 使用 md5sum 校验文件
> # 使用包含特定文件的MD5 哈希值的文件对文件完整性进行校验
> md5sum -c checksums.md5
> # checksums.md5 是包含哈希值的文件。
> # 如果文件的哈希值与 checksums.md5 文件中的哈希值匹配，md5sum 将不会输出任何内容；
> # 如果不匹配，它将显示不匹配的文件名。
> ```
>
>
> ```markdown title="更新文件的 MD5 哈希值"
> # 更新文件的 MD5 哈希值
> md5sum -u filename >> checksums.md5
>
> ```
>
>
> ```markdown title="静默模式"
> # 静默模式
> # 如果不想看到任何输出，可以使用静默模式
> md5sum -s filename
> # 这将不输出任何内容，但会返回退出状态码，0 表示成功，1 表示失败
> ```
>

[^1]: [https://en.wikipedia.org/wiki/Md5sum](https://en.wikipedia.org/wiki/Md5sum "https://en.wikipedia.org/wiki/Md5sum")
