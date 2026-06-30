"""数据下载相关 DTO"""

from typing import Literal

from pydantic import Field

from omichub.application.schemas.base import OmicsHubBaseSchema


class DownloadRequest(OmicsHubBaseSchema):
    """数据下载请求"""

    accession: str = Field(description="EBI/NCBI 登录号，如 PRJNA1251654 或 SRRxxxxxx")
    download_method: Literal["aws", "aspera", "ftp"] = Field(default="aws", description="下载方式")
    multithreads: int = Field(default=4, ge=1, le=32, description="并发下载数")
    aws_threads: int = Field(default=8, ge=1, le=64, description="单文件 AWS 并发线程数")
