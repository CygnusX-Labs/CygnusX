"""文件域值对象"""

from enum import Enum


class FileType(str, Enum):
    """文件类型"""

    FASTQ = "fastq"
    BAM = "bam"
    VCF = "vcf"
    COUNT_MATRIX = "count_matrix"
    H5AD = "h5ad"
    RDS = "rds"
    META = "meta"
    REPORT = "report"
    IMAGE = "image"
    OTHER = "other"


class UploadStatus(str, Enum):
    """上传状态"""

    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
