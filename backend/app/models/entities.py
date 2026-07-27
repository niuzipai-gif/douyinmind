"""
数据表实体定义模块

定义项目所有数据表的 ORM 模型：
- FavoriteCollection：抖音收藏夹
- FavoriteVideo：收藏夹中的视频
- VideoCache：视频入库缓存与 ASR 转写结果
- ChatSession：对话会话
- ChatMessage：对话消息
"""
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FavoriteCollection(Base):
    """
    抖音收藏夹

    存储从抖音同步的收藏夹元信息。
    """

    __tablename__ = "favorite_collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    """主键 ID"""

    platform_collection_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    """抖音收藏夹 ID"""

    title: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    """收藏夹名称"""

    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """收藏夹内视频数量"""

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """是否有效（软删除标记）"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    """创建时间"""

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    """更新时间"""

    # 关联
    videos: Mapped[list["FavoriteVideo"]] = relationship(
        "FavoriteVideo", back_populates="collection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FavoriteCollection id={self.id} title='{self.title}'>"


class FavoriteVideo(Base):
    """
    收藏夹中的视频

    存储从抖音收藏夹拉取的视频元信息。
    """

    __tablename__ = "favorite_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    """主键 ID"""

    collection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("favorite_collections.id"), nullable=False, index=True
    )
    """所属收藏夹 ID"""

    platform_item_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    """抖音视频 ID"""

    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    """视频标题"""

    author: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    """视频作者"""

    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """视频时长（秒）"""

    cover_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    """视频封面图片 URL"""

    video_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    """视频/音频下载 URL"""

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    """是否有效（软删除标记）"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    """创建时间"""

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    """更新时间"""

    # 关联
    collection: Mapped["FavoriteCollection"] = relationship(
        "FavoriteCollection", back_populates="videos"
    )

    def __repr__(self) -> str:
        return f"<FavoriteVideo id={self.id} title='{self.title}'>"


class VideoCache(Base):
    """
    视频入库缓存

    记录每个视频的入库处理状态和 ASR 转写结果。
    入库流程：pending → downloading → transcribing → done
    异常状态：failed
    """

    __tablename__ = "video_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    """主键 ID"""

    platform_item_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    """抖音视频 ID"""

    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    """视频标题（缓存副本，避免关联查询）"""

    transcript_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    """ASR 转写全文"""

    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    """AI 摘要（预留）"""

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    """
    处理状态：
    - pending: 等待处理
    - downloading: 正在下载音频
    - transcribing: 正在语音转写
    - done: 处理完成
    - failed: 处理失败
    """

    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    """失败时的错误信息"""

    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    """处理完成时间"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    """创建时间"""

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    """更新时间"""

    def __repr__(self) -> str:
        return f"<VideoCache platform_item_id='{self.platform_item_id}' status='{self.status}'>"


class ChatSession(Base):
    """
    对话会话

    每次问答归属一个会话，支持多轮对话。
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    """主键 ID"""

    title: Mapped[str] = mapped_column(String(128), nullable=False, default="New Chat")
    """会话标题（默认取首条用户消息前 40 字）"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    """创建时间"""

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    """更新时间"""

    # 关联
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} title='{self.title}'>"


class ChatMessage(Base):
    """
    对话消息

    记录每次问答的用户消息和助手回复。
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    """主键 ID"""

    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    """所属会话 ID"""

    role: Mapped[str] = mapped_column(String(16), nullable=False)
    """
    消息角色：
    - user: 用户提问
    - assistant: 助手回复
    """

    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    """消息内容"""

    route_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="direct"
    )
    """
    路由类型：
    - direct: 直接回复（问候等不需要检索的场景）
    - vector: 向量检索 + RAG
    - db_list: 数据库列表查询
    - db_content: 数据库内容概览
    """

    retrieved_video_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    """召回的视频 ID 列表（JSON 数组字符串）"""

    retrieved_chunk_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    """召回的 chunk ID 列表（JSON 数组字符串）"""

    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    """使用的 LLM 模型名称"""

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """请求延迟（毫秒），仅 assistant 角色记录"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    """创建时间"""

    # 关联
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role='{self.role}' session_id={self.session_id}>"
