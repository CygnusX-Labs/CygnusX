# 腾讯云ECS

#### Rstudio

![](image/image_245rI9-Jcr.png)

> **NOTE** : 可以打开服务器所有端口，但是该操作存在很大的分险
>
> [ 在云服务器中运行Rstudio中遇到的一些小问题\_租服务器跑r语言-CSDN博客 文章浏览阅读1.4k次。最近要跑一些比较慢的R程序（菜鸡代码优化的不好），租用了一台腾讯云服务器，根据网上大家分享的教程进行了环境配置和软件的部署，中间也遇到了一些小问题，一些解决方案与大家分享。1.有用的R和Rstudio配置教程，感谢这位知乎博主，侵删https://zhuanlan.zhihu.com/p/133482023注意：在登录云服务器时，要求输password时，密码不显示是正常的 https://blog.csdn.net/feihua1475/article/details/118963628](https://blog.csdn.net/feihua1475/article/details/118963628 " 在云服务器中运行Rstudio中遇到的一些小问题_租服务器跑r语言-CSDN博客 文章浏览阅读1.4k次。最近要跑一些比较慢的R程序（菜鸡代码优化的不好），租用了一台腾讯云服务器，根据网上大家分享的教程进行了环境配置和软件的部署，中间也遇到了一些小问题，一些解决方案与大家分享。1.有用的R和Rstudio配置教程，感谢这位知乎博主，侵删https://zhuanlan.zhihu.com/p/133482023注意：在登录云服务器时，要求输password时，密码不显示是正常的 https://blog.csdn.net/feihua1475/article/details/118963628")

#### jupyter-lab

```python title="jupyter-lab"
jupyter-lab --no-browser --ip=0.0.0.0 --port=8887
```


![](<image/截屏2024-05-28 23.04.33_tMQKtCZiBT.png>)
