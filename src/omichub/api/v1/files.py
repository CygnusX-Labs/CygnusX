"""文件路由"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/samples")
async def list_samples():
    """获取样本列表"""
    return {"message": "list samples"}


@router.post("/upload")
async def upload_file():
    """上传文件"""
    return {"message": "upload file"}


@router.get("/{file_id}/download")
async def download_file(file_id: str):
    """下载文件"""
    return {"file_id": file_id}
