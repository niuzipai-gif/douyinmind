"""
收藏夹路由模块

提供收藏夹同步、列表查询、视频列表等接口。
"""
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.favorites_service import favorites_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/favorites", tags=["收藏夹"])


@router.post("/sync")
async def sync_favorites(db: Session = Depends(get_db)):
    """
    从抖音同步收藏夹数据

    拉取最新收藏夹和视频列表，与本地数据库差异对齐。
    新增的视频会自动创建 VideoCache pending 记录，供阶段 3 入库使用。

    :param db: 数据库会话
    :return: 同步结果统计
    """
    try:
        result = await favorites_service.sync_from_douyin(db)
        return {"success": True, **result}
    except Exception as exc:
        import traceback
        logger.error("收藏夹同步失败: %s\n%s", exc, traceback.format_exc())
        return {"success": False, "message": f"{type(exc).__name__}: {exc}"}


@router.get("/collections")
async def list_collections(db: Session = Depends(get_db)):
    """
    获取已同步的收藏夹列表

    第一项固定为"全部收藏"。

    :param db: 数据库会话
    :return: 收藏夹列表
    """
    items = favorites_service.list_collections(db)
    return {
        "success": True,
        "items": items,
        "total": len(items),
    }


@router.get("/collections/{collection_id}/videos")
async def list_collection_videos(
    collection_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    获取指定收藏夹的视频列表（分页）

    :param collection_id: 收藏夹 ID（"all" 表示全部收藏）
    :param page: 页码（从 1 开始）
    :param size: 每页数量（1-100）
    :param db: 数据库会话
    :return: 分页视频列表
    """
    items, total = favorites_service.list_collection_videos(
        db, collection_id, page=page, size=size
    )
    return {
        "success": True,
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }
