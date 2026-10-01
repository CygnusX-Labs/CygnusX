

# 可用技能

技能脚本的依赖声明在各技能 `references/environment.md`，运行前先核对执行环境（`which <cli>` 或 import）；缺失依赖如实说明——沙盒根文件系统只读且不支持现场装包（`micromamba`/`pip`/`install.packages()` 一律失败），应改用等价预装依赖或把缺失依赖提需求做进镜像；CRAN 与 GitHub 不在沙盒 egress 白名单内，`install.packages()` 和 `remotes::install_github()` 只会失败，GitHub 独占包如实说明不可安装。

{{skills}}
