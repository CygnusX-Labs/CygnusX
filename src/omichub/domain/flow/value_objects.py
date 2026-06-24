"""流程域值对象"""

from enum import Enum
from typing import Any


class ParamType(str, Enum):
    """参数类型"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SELECT = "select"
    FILE = "file"
    SAMPLE = "sample"
    TEXT = "text"


class FlowCategory(str, Enum):
    """流程类别"""

    RNA_SEQ = "rna-seq"
    SC_RNA_SEQ = "sc-rna-seq"
    ATAC_SEQ = "atac-seq"
    VARIANT = "variant"
    METHYLATION = "methylation"
    PROTEOMICS = "proteomics"
    OTHER = "other"


class UIControl(str, Enum):
    """UI 控件类型"""

    INPUT = "input"
    NUMBER = "number"
    SELECT = "select"
    SLIDER = "slider"
    SWITCH = "switch"
    FILE_UPLOAD = "file_upload"
    SAMPLE_SELECTOR = "sample_selector"
    TEXTAREA = "textarea"
