"""
知识库入库服务模块

编排视频入库流水线：
1. 从 VideoCache 获取 pending 状态的视频
2. 下载音频 → ASR 转写 → 文本切块 → Embedding → 存入 ChromaDB
3. 更新 VideoCache 状态
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import VideoCache
from app.services.asr_service import asr_service
from app.services.chroma_service import get_chroma_service
from app.services.llm_service import embedding_client
from app.services.media_service import download_audio
from app.services.text_processing import build_fixed_chunks
from app.services.worker import worker

logger = logging.getLogger(__name__)


class KnowledgeService:
    """
    知识库入库服务

    负责：
    1. 触发入库任务
    2. 逐视频执行入库流水线
    3. 提供知识库统计
    """

    def start_sync(
        self, db: Session, selected_ids: list[str] | None = None
    ) -> dict:
        """
        启动入库任务

        查询 pending 状态的视频（或指定视频），提交到后台 worker 逐个处理。

        :param db: 数据库会话
        :param selected_ids: 可选，限定入库的视频 ID 列表
        :return: {"task_id": ..., "pending_count": ...}
        """
        # 查询待处理的视频
        query = select(VideoCache).where(
            VideoCache.status == "pending"
        )
        pending_videos = db.execute(query).scalars().all()

        # 按选定 ID 过滤
        if selected_ids:
            id_set = set(selected_ids)
            pending_videos = [v for v in pending_videos if v.platform_item_id in id_set]

        if not pending_videos:
            return {
                "task_id": None,
                "pending_count": 0,
                "message": "没有待入库的视频，请先同步收藏夹",
            }

        task_id = str(uuid.uuid4())[:8]
        worker.submit(
            task_id,
            self._run_sync,
            db,
            [v.platform_item_id for v in pending_videos],
        )

        return {
            "task_id": task_id,
            "pending_count": len(pending_videos),
            "message": f"已提交入库任务，共 {len(pending_videos)} 个视频",
        }

    def _run_sync(
        self,
        db: Session,
        platform_item_ids: list[str],
        task_id: str = "",
    ) -> None:
        """
        执行入库流水线（在后台线程中运行）

        逐个处理待入库视频：
        pending → downloading → transcribing → embedding → done

        :param db: 数据库会话
        :param platform_item_ids: 待处理的视频 ID 列表
        :param task_id: 任务 ID（由 worker 回调传入）
        """
        total = len(platform_item_ids)
        chroma = get_chroma_service()

        for idx, platform_item_id in enumerate(platform_item_ids):
            # 获取视频缓存记录
            cache = db.execute(
                select(VideoCache).where(
                    VideoCache.platform_item_id == platform_item_id
                )
            ).scalar_one_or_none()

            if cache is None:
                logger.warning("VideoCache 记录不存在: %s", platform_item_id)
                continue

            try:
                # 构建视频 URL
                video_url = f"https://www.douyin.com/video/{platform_item_id}"

                # Step 1: 下载音频
                cache.status = "downloading"
                db.commit()
                worker.update_progress(
                    task_id, idx + 1, total,
                    f"下载音频: {cache.title[:30]}...",
                )
                audio_path = download_audio(video_url, platform_item_id)

                # Step 2: ASR 转写
                cache.status = "transcribing"
                db.commit()
                worker.update_progress(
                    task_id, idx + 1, total,
                    f"语音转写: {cache.title[:30]}...",
                )
                transcript_text = asr_service.transcribe_to_text(
                    audio_path
                )
                cache.transcript_text = transcript_text

                # Step 3: 文本切块
                chunks = build_fixed_chunks(transcript_text)
                if not chunks:
                    logger.warning(
                        "转写内容为空: %s", platform_item_id
                    )
                    cache.status = "failed"
                    cache.error_message = "转写内容为空"
                    db.commit()
                    continue

                # 追加元信息文档（标题 + 作者搜索召回优化）
                from app.models.entities import FavoriteVideo as FV
                fv = db.query(FV).filter(
                    FV.platform_item_id == platform_item_id
                ).first()
                meta_chunk = f"视频标题：{cache.title}"
                if fv and fv.author:
                    meta_chunk += f"\n作者：{fv.author}"
                chunks = [meta_chunk] + chunks

                # Step 4: Embedding + 存入 ChromaDB
                worker.update_progress(
                    task_id, idx + 1, total,
                    f"向量化入库: {cache.title[:30]}...",
                )
                embeddings = embedding_client.embed_texts(chunks)
                chroma.upsert_video_chunks(
                    platform_item_id=platform_item_id,
                    title=cache.title,
                    chunks=chunks,
                    embeddings=embeddings,
                )

                # Step 5: 标记完成
                cache.status = "done"
                db.commit()

                logger.info(
                    "入库成功 (%d/%d): %s (%d chunks)",
                    idx + 1,
                    total,
                    platform_item_id,
                    len(chunks),
                )

                # 清理临时音频文件
                try:
                    audio_path.unlink(missing_ok=True)
                except Exception:
                    pass

            except Exception as exc:
                logger.exception(
                    "入库失败 (%d/%d): %s", idx + 1, total, platform_item_id
                )
                cache.status = "failed"
                cache.error_message = str(exc)[:1000]
                db.commit()

    def get_stats(self, db: Session) -> dict:
        """
        获取知识库统计信息

        :param db: 数据库会话
        :return: 统计数据
        """
        # 各状态视频数量
        pending = db.scalar(
            select(func.count()).select_from(VideoCache).where(
                VideoCache.status == "pending"
            )
        ) or 0
        done = db.scalar(
            select(func.count()).select_from(VideoCache).where(
                VideoCache.status == "done"
            )
        ) or 0
        failed = db.scalar(
            select(func.count()).select_from(VideoCache).where(
                VideoCache.status == "failed"
            )
        ) or 0
        downloading = db.scalar(
            select(func.count()).select_from(VideoCache).where(
                VideoCache.status == "downloading"
            )
        ) or 0
        transcribing = db.scalar(
            select(func.count()).select_from(VideoCache).where(
                VideoCache.status == "transcribing"
            )
        ) or 0

        # ChromaDB 统计
        chroma = get_chroma_service()
        chroma_chunks = chroma.count()
        chroma_videos = chroma.get_video_count()

        return {
            "video_cache": {
                "pending": int(pending),
                "downloading": int(downloading),
                "transcribing": int(transcribing),
                "done": int(done),
                "failed": int(failed),
            },
            "chromadb": {
                "total_chunks": chroma_chunks,
                "total_videos": chroma_videos,
            },
        }

    def get_progress(self, task_id: str) -> dict | None:
        """
        查询入库任务进度

        :param task_id: 任务 ID
        :return: 进度信息
        """
        return worker.get_progress(task_id)


    def delete_video(self, db: Session, platform_item_id: str) -> dict:
        """
        删除已入库视频

        清理 ChromaDB 向量、重置 VideoCache 状态、删除音频缓存。

        :param db: 数据库会话
        :param platform_item_id: 抖音视频 ID
        :return: 删除结果
        :raises ValueError: 视频不存在或正在入库中
        """
        cache = db.query(VideoCache).filter(
            VideoCache.platform_item_id == platform_item_id
        ).first()

        if cache is None:
            raise ValueError(f"视频 {platform_item_id} 不存在")
        if cache.status in ("downloading", "transcribing"):
            raise ValueError("视频正在入库中，无法删除")

        # 1. 删除 ChromaDB 向量
        chroma = get_chroma_service()
        chroma.delete_by_video(platform_item_id)

        # 2. 重置 VideoCache
        cache.status = "pending"
        cache.transcript_text = ""
        cache.error_message = ""
        cache.processed_at = None

        # 3. 清理音频缓存
        audio_dir = Path(settings.audio_cache_dir)
        for ext in (".mp3", ".wav", ".m4a", ".webm", ".opus"):
            audio_file = audio_dir / f"{platform_item_id}{ext}"
            if audio_file.exists():
                audio_file.unlink(missing_ok=True)

        db.commit()
        logger.info("视频已删除: %s", platform_item_id)
        return {"platform_item_id": platform_item_id, "status": "pending"}


# 全局单例
knowledge_service = KnowledgeService()
