"""
知识库路由模块

提供收藏夹一键入库、入库进度查询、知识库统计、视频内容导出等接口。
"""
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import VideoCache
from app.services.knowledge_service import knowledge_service
from app.services.markdown_export import export_ai_organized, export_original
from app.services.worker import worker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["知识库"])


class SyncRequest(BaseModel):
    selected_ids: list[str] = []

@router.post("/sync")
async def sync_knowledge(body: SyncRequest, db: Session = Depends(get_db)):
    """
    触发知识库入库任务

    将 pending 状态的视频（或指定的视频）提交到后台 worker，
    逐个执行：下载音频 → ASR 转写 → 切块 → 向量化 → 存入 ChromaDB。

    :param body: 请求体，可指定 selected_ids 限定入库范围
    :param db: 数据库会话
    :return: 任务 ID 和待处理数量
    """
    result = knowledge_service.start_sync(db, body.selected_ids or None)
    return {"success": True, **result}


@router.get("/sync/{task_id}")
async def get_sync_progress(task_id: str):
    """
    查询入库任务进度

    :param task_id: 任务 ID（由 /sync 返回）
    :return: 任务状态和进度
    """
    progress = knowledge_service.get_progress(task_id)
    if progress is None:
        return {
            "success": False,
            "message": f"任务不存在: {task_id}",
        }
    return {"success": True, **progress}


@router.post("/reset-failed")
async def reset_failed_videos(db: Session = Depends(get_db)):
    """
    将所有失败/卡住的视频重置为 pending

    处理场景：
    - 入库过程被中断（刷新页面、服务重启）
    - 视频转写失败需要重试

    :param db: 数据库会话
    :return: 重置数量
    """
    from sqlalchemy import update as sql_update
    reset_statuses = ["failed", "downloading", "transcribing"]
    result = db.execute(
        sql_update(VideoCache)
        .where(VideoCache.status.in_(reset_statuses))
        .values(status="pending", error_message="")
    )
    db.commit()
    count = result.rowcount
    return {"success": True, "reset_count": count}


@router.delete("/videos/{platform_item_id}")
async def delete_video(platform_item_id: str, db: Session = Depends(get_db)):
    """
    删除已入库视频

    清理 ChromaDB 向量、重置为 pending 状态、删除音频缓存。
    不允许删除正在入库中的视频。

    :param platform_item_id: 抖音视频 ID
    :param db: 数据库会话
    :return: 删除结果
    """
    try:
        result = knowledge_service.delete_video(db, platform_item_id)
        return {"success": True, **result}
    except ValueError as exc:
        return {"success": False, "message": str(exc)}


@router.get("/stats")
async def get_knowledge_stats(db: Session = Depends(get_db)):
    """
    获取知识库统计信息

    :param db: 数据库会话
    :return: VideoCache 各状态数量 + ChromaDB 存储统计
    """
    stats = knowledge_service.get_stats(db)
    return {"success": True, **stats}


@router.get("/export/{platform_item_id}", response_class=PlainTextResponse)
async def export_video_markdown(
    platform_item_id: str,
    mode: str = Query("original", pattern="^(original|ai)$"),
    db: Session = Depends(get_db),
):
    """
    导出视频内容为 Markdown

    两种模式：
    - original：原始 ASR 转写全文 + 元信息
    - ai：AI 结构化整理（摘要/观点/提纲/建议）+ 原始转写

    :param platform_item_id: 抖音视频 ID
    :param mode: 导出模式（original / ai）
    :param db: 数据库会话
    :return: Markdown 文本（Content-Type: text/plain; charset=utf-8）
    """
    cache = db.execute(
        select(VideoCache).where(VideoCache.platform_item_id == platform_item_id)
    ).scalar_one_or_none()

    if cache is None:
        return f"# 导出失败\n\n视频 `{platform_item_id}` 未找到，请先同步收藏夹。\n"

    try:
        if mode == "original":
            md = export_original(cache)
        else:
            md = export_ai_organized(cache)
    except ValueError as exc:
        return f"# 导出失败\n\n{exc}\n"

    from fastapi.responses import Response
    return Response(
        content=md,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={platform_item_id}.md"
        },
    )
