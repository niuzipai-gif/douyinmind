"""
RAG 问答服务模块

核心问答流水线：
1. 查询路由（规则匹配）
2. 向量语义检索
3. 上下文构建 + 历史注入
4. LLM 生成回答（非流式 / SSE 流式）
5. 答案后处理
6. 会话与消息持久化
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import (
    ChatMessage,
    ChatSession,
    FavoriteVideo,
    VideoCache,
)
from app.services.chroma_service import get_chroma_service
from app.services.llm_service import embedding_client, llm_client

logger = logging.getLogger(__name__)

# ==================================================================
# 静态工具函数
# ==================================================================

_GREETING_KEYWORDS = [
    "你好", "在吗", "hi", "hello", "你是谁", "谢谢", "早上好", "晚安",
]


def _is_greeting(query: str) -> bool:
    """判断是否为问候语"""
    low = query.lower().strip()
    return any(kw in low for kw in _GREETING_KEYWORDS)


def _is_list_query(query: str) -> bool:
    """判断是否为列举类查询（如'有哪些视频'）"""
    return bool(
        re.search(r"有哪些|列表|清单|目录|都有什么|列出|哪些", query)
    )


def _is_summary_query(query: str) -> bool:
    """判断是否为总结类查询（如'总结一下'）"""
    return bool(
        re.search(r"总结|概述|概括|回顾|梳理|整体|全部|全库", query)
    )


def _is_structured_query(query: str) -> bool:
    """判断是否需要结构化输出"""
    return bool(
        re.search(r"总结|对比|步骤|清单|列表|框架|归纳", query)
    )


def _normalize_query(query: str) -> str:
    """规范化查询文本"""
    query = query.strip()
    query = re.sub(r"\s+", " ", query)
    return query


def _sanitize_answer(text: str, is_structured: bool) -> str:
    """
    清洗 LLM 输出

    - 去除 Markdown 标题符号
    - 处理表格行（| 分隔的管道符）
    - 格式化列表项
    - 口语化段落合并

    :param text: LLM 原始输出
    :param is_structured: 是否允许结构化格式
    :return: 清洗后的文本
    """
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return text

    # 去除 Markdown 标题符号
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)

    clean_lines: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            clean_lines.append("")
            continue

        # 跳过纯分隔线
        if re.fullmatch(r"[\|\-:\s]+", line):
            continue

        # 处理表格
        if "|" in line:
            parts = [
                part.strip() for part in line.split("|") if part.strip()
            ]
            line = " ".join(parts) if parts else ""
            if not line:
                continue

        # 处理无序列表
        bullet_match = re.match(r"^\s*[-*•]\s+(.*)$", line)
        if bullet_match:
            line = bullet_match.group(1).strip()

        # 去除格式标记
        line = re.sub(r"[`*_]{1,3}", "", line).strip()
        if line:
            clean_lines.append(line)

    merged = "\n".join(clean_lines)
    # 非结构化输出：合并段落
    if not is_structured:
        merged = re.sub(r"(?<![。！？.!?：:])\n(?!\n)", " ", merged)
    merged = re.sub(r"\n{3,}", "\n\n", merged).strip()
    return merged


# ==================================================================
# RAG 服务
# ==================================================================


class RagService:
    """
    RAG 问答服务

    负责端到端的检索增强生成流程。
    """

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------

    def _route(self, query: str, has_data: bool) -> str:
        """
        查询路由分发

        规则优先级：问候 > 列表 > 总结 > 向量检索

        :param query: 用户问题
        :param has_data: 知识库是否有数据
        :return: 路由类型（direct / db_list / db_content / vector）
        """
        if _is_greeting(query):
            return "direct"
        if _is_list_query(query):
            return "db_list"
        if _is_summary_query(query):
            # 带话题限定词的总结（如"总结技术类视频"）走语义检索
            # 纯"总结一下"/"概括"才走 db_content
            topic_words = re.sub(
                r'总结|概述|概括|回顾|梳理|整体|全部|全库|一下|帮我|一下',
                '', query
            ).strip()
            if topic_words:
                return "vector"
            return "db_content"
        if not has_data:
            return "direct"
        return "vector"

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def _dense_retrieve(
        self, query: str, scope_ids: set[str] | None = None, top_k: int | None = None
    ) -> list[dict]:
        """
        向量语义检索

        :param query: 用户问题
        :param scope_ids: 限定检索的视频 ID 集合（None=全库）
        :param top_k: 返回数量
        :return: 检索结果列表
        """
        k = top_k or settings.retrieval_top_k
        query_vector = embedding_client.embed_text(query)
        chroma = get_chroma_service()
        hits = chroma.search(
            query_vector, top_k=k,
            use_mmr=True,
            fetch_k=settings.retrieval_mmr_fetch_k,
            lambda_mult=settings.retrieval_mmr_lambda,
        )

        # 按收藏夹范围过滤
        if scope_ids:
            hits = [h for h in hits if h["platform_item_id"] in scope_ids]
        return hits[:k]

    def _resolve_collection_scope(
        self, db: Session, collection_id: str
    ) -> set[str]:
        """
        解析收藏夹 ID → 包含的 platform_item_id 集合

        :param db: 数据库会话
        :param collection_id: 收藏夹 platform_collection_id
        :return: 视频 ID 集合
        """
        from app.models.entities import FavoriteCollection, FavoriteVideo
        collection = db.query(FavoriteCollection).filter(
            FavoriteCollection.platform_collection_id == collection_id,
            FavoriteCollection.is_active.is_(True),
        ).first()
        if not collection:
            return set()
        rows = db.query(FavoriteVideo.platform_item_id).filter(
            FavoriteVideo.collection_id == collection.id,
            FavoriteVideo.is_active.is_(True),
        ).all()
        return {r[0] for r in rows}

    # ------------------------------------------------------------------
    # 上下文构建
    # ------------------------------------------------------------------

    def _build_context(
        self, route: str, hits: list[dict], db: Session, query: str = ""
    ) -> str:
        """
        根据路由类型构建 LLM 上下文

        :param route: 路由类型
        :param hits: 检索结果（仅 vector 路由使用）
        :param db: 数据库会话
        :param query: 用户问题（用于 Map-Reduce 压缩）
        :return: 格式化后的上下文文本
        """
        if route == "db_list":
            return self._db_list_context(db)
        if route == "db_content":
            # db_content 也走语义检索 + 压缩，而不只是查 DB
            if hits:
                return self._compress_chunks(query, hits[: settings.rag_context_count])
            return self._db_content_context(db)
        if route == "vector" and hits:
            return self._compress_chunks(
                query=query,
                hits=hits[: settings.rag_context_count]
            )
        return ""

    def _db_list_context(self, db: Session) -> str:
        """
        构建视频列表上下文

        :param db: 数据库会话
        :return: 格式化的视频清单
        """
        rows = (
            db.query(VideoCache)
            .filter(VideoCache.status == "done")
            .limit(120)
            .all()
        )
        if not rows:
            return ""
        return "\n".join(
            f"- {row.title} ({row.platform_item_id})" for row in rows
        )

    def _db_content_context(self, db: Session) -> str:
        """
        构建内容摘要上下文

        :param db: 数据库会话
        :return: 最近入库视频的内容片段
        """
        rows = (
            db.query(VideoCache)
            .filter(VideoCache.status == "done")
            .order_by(desc(VideoCache.processed_at))
            .limit(10)
            .all()
        )
        if not rows:
            return ""

        parts = []
        for row in rows:
            excerpt = (row.transcript_text or "")[:800]
            if not excerpt:
                continue
            parts.append(f"【{row.title}】\n{excerpt}")
        return "\n\n---\n\n".join(parts)

    def _history_context(
        self, db: Session, session_id: int | None
    ) -> str:
        """
        获取历史对话窗口

        :param db: 数据库会话
        :param session_id: 会话 ID
        :return: 格式化的历史对话
        """
        if not session_id:
            return ""

        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(
                ChatMessage.created_at.desc(), ChatMessage.id.desc()
            )
            .limit(settings.chat_history_window)
            .all()
        )
        if not rows:
            return ""

        rows = list(reversed(rows))
        lines: list[str] = []
        for row in rows:
            role = "用户" if row.role == "user" else "助手"
            content = (row.content or "").strip()
            if not content:
                continue
            if len(content) > settings.chat_max_content_chars:
                content = (
                    content[: settings.chat_max_content_chars] + "..."
                )
            lines.append(f"{role}: {content}")

        return "\n".join(lines)

    def _compress_chunks(self, query: str, hits: list[dict]) -> str:
        """
        Map-Reduce 上下文压缩

        当检索到的 chunk 数 > 3 时，先对每个 chunk 独立做摘要压缩，
        再拼成最终上下文。少量 chunk（≤3）直接拼接，不增加额外 LLM 调用。

        :param query: 用户问题
        :param hits: 检索结果列表
        :return: 压缩后的上下文字符串
        """
        if len(hits) <= 3:
            return "\n\n".join(
                f"【{h['title']}】\n{h['text']}" for h in hits
            )

        compressed: list[str] = []
        for h in hits[:8]:
            try:
                summary = llm_client.chat(
                    system_prompt=(
                        "你是一个精炼的摘要员。只输出 3 条核心要点，"
                        "每条不超过 25 字。不要添加任何额外说明。"
                    ),
                    user_prompt=f"问题：{query}\n\n内容：\n{h['text']}",
                    temperature=0.1,
                    max_tokens=200,
                )
                compressed.append(f"【{h['title']}】\n{summary.strip()}")
            except Exception:
                # 压缩失败时用原始文本
                compressed.append(f"【{h['title']}】\n{h['text'][:300]}")

        # 相邻 chunk 去重：移除重复的句子开头
        deduped = [compressed[0]] if compressed else []
        for i in range(1, len(compressed)):
            prev = deduped[-1]
            curr = compressed[i]
            # 找两个 chunk 的最长公共前缀
            min_len = min(len(prev), len(curr))
            overlap_at = 0
            for j in range(20, min_len, 10):
                if prev[-j:] == curr[:j]:
                    overlap_at = j
            if overlap_at > 30:
                curr = curr[overlap_at:].lstrip("，。、；：！？\n ")
            deduped.append(curr)

        return "\n\n---\n\n".join(deduped)

    @staticmethod
    def _truncate_context(context: str, max_chars: int | None = None) -> str:
        """
        截断过长上下文

        :param context: 原始上下文
        :param max_chars: 最大字符数
        :return: 截断后的上下文
        """
        if not context:
            return ""
        cap = max_chars or settings.rag_prompt_max_context_chars
        if cap <= 0:
            return context
        if len(context) <= cap:
            return context
        return context[:cap] + "\n\n[内容过长，已截断]"

    # ------------------------------------------------------------------
    # 提示词
    # ------------------------------------------------------------------

    @staticmethod
    def _answer_style(is_structured: bool) -> str:
        """生成回答风格指令"""
        if is_structured:
            return (
                "输出要求：\n"
                "1) 语气自然、像对话，不要生硬模板。\n"
                "2) 可用轻结构（最多3点），每点用完整句。\n"
                "3) 禁止 Markdown 表格和标题符号。\n"
            )
        return (
            "输出要求：\n"
            "1) 用自然口语化短段落回答，像真人交流。\n"
            "2) 先直接回答，再补充必要细节，段落间要有过渡。\n"
            "3) 禁止 Markdown 表格和标题符号。\n"
        )

    def _build_prompts(
        self,
        route: str,
        query: str,
        context: str,
        history: str,
    ) -> tuple[str, str, bool]:
        """
        构建 System / User 提示词

        :param route: 路由类型
        :param query: 用户问题
        :param context: 检索/查询到的上下文
        :param history: 历史对话
        :return: (system_prompt, user_prompt, is_structured)
        """
        is_structured = _is_structured_query(query)
        style = self._answer_style(is_structured)
        history_block = (
            f"最近对话历史：\n{history}\n\n" if history else ""
        )

        if route == "direct":
            system = (
                "你是一个自然友好的助手，用口语化方式回答问题。\n"
                f"{style}"
            )
            user = f"{history_block}当前问题：{query}"
            return system, user, is_structured

        if route == "db_list":
            system = (
                "你是收藏夹知识库助手。用户询问视频清单/目录。"
                "先给直接结论，再列举要点。\n"
                f"{style}"
            )
            user = f"{history_block}问题：{query}\n\n已入库视频清单：\n{context}"
            return system, user, is_structured

        if route == "db_content":
            system = (
                "你是收藏夹知识库助手。用户要求对知识库内容做归纳总结。\n\n"
                "请按以下格式输出：\n"
                "## TL;DR\n"
                "先用 3 条 bullet 给出最核心的结论，每条不超过 30 字。\n\n"
                "## 共同主题\n"
                "从所有内容中提炼跨视频的共性关键词（不超过 5 个），"
                "说明为什么这些是共同主题。\n\n"
                "## 各视频要点\n"
                "逐视频列出核心观点，每个要点后标注 [来源: 标题]。"
                "如果某个视频的内容与用户问的话题无关，直接跳过不写。\n\n"
                "约束：\n"
                "- TL;DR 必须出现在最前面\n"
                "- 总字数不超过 500 字，优先讲最重要的 3 个视频\n"
                "- 每个观点必须标注来自哪个视频，格式 [来源: xxx]\n"
            )
            user = f"{history_block}问题：{query}\n\n内容片段：\n{context}"
            return system, user, is_structured

        # vector 路由 — 检测到总结类问题时追加归纳要求
        extra = ""
        if _is_summary_query(query):
            extra = (
                "\n注意用户问的是归纳总结。请：\n"
                "1. 先提炼跨视频的共同主题，再逐视频简述\n"
                "2. 每个观点后标注 [来源: 标题]\n"
                "3. 总字数不超过 500 字，只讲最相关的\n"
            )
        system = (
            "你是视频知识库问答助手。基于检索到的内容回答。"
            "先给直接结论，再简要佐证。\n"
            f"{style}{extra}"
        )
        user = f"{history_block}问题：{query}\n\n相关内容：\n{context}"
        return system, user, is_structured

    def _ensure_sources(self, answer: str, sources: list[dict]) -> str:
        """
        如果回答中没有 [来源: xxx] 标注，自动追加来源清单

        :param answer: LLM 生成的回答
        :param sources: 来源视频列表
        :return: 补充来源后的回答
        """
        if not sources:
            return answer
        if re.search(r'\[来源[:：]', answer):
            return answer

        lines = ["", "---", "📎 **参考来源：**"]
        seen: set[str] = set()
        for s in sources[:5]:
            title = s.get("title", "")
            url = s.get("url", "")
            if title and title not in seen:
                seen.add(title)
                lines.append(f"- [{title}]({url})")
        return answer + "\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # 非流式回答
    # ------------------------------------------------------------------

    def answer(
        self,
        db: Session,
        query: str,
        session_id: int | None,
        collection_id: str | None = None,
    ) -> dict:
        """
        非流式 RAG 问答

        完整流程：
        路由 → 检索 → 构建上下文 → LLM 生成 → 持久化

        :param db: 数据库会话
        :param query: 用户问题
        :param session_id: 会话 ID（可选，新建会话时为空）
        :param collection_id: 限定检索的收藏夹 ID（可选，all/空=全库）
        :return: {"answer": ..., "sources": ..., "session_id": ..., "route_type": ...}
        """
        started = time.perf_counter()

        # Step 1: 路由
        t0 = time.perf_counter()
        normalized = _normalize_query(query)
        chroma = get_chroma_service()
        has_data = chroma.count() > 0
        route = self._route(normalized, has_data)
        t_route = time.perf_counter() - t0

        # Step 2: 检索（支持收藏夹筛选）
        t0 = time.perf_counter()
        hits: list[dict] = []
        if route == "vector":
            # 解析收藏夹范围 → platform_item_id 列表
            scope_ids: set[str] | None = None
            if collection_id and collection_id not in ("all", ""):
                scope_ids = self._resolve_collection_scope(db, collection_id)
            hits = self._dense_retrieve(normalized, scope_ids)
        t_dense = time.perf_counter() - t0

        # Step 3: 构建上下文
        t0 = time.perf_counter()
        context = self._truncate_context(
            self._build_context(route, hits, db, normalized)
        )

        # Step 4: 历史对话
        history = self._history_context(db, session_id)
        system, user, is_structured = self._build_prompts(
            route, normalized, context, history
        )
        t_ctx = time.perf_counter() - t0

        # Step 5: LLM 生成
        t0 = time.perf_counter()
        answer = llm_client.chat(
            system_prompt=system,
            user_prompt=user,
        )
        answer = _sanitize_answer(answer, is_structured)
        # 提前构建来源列表（_ensure_sources 需要）
        sources: list[dict] = []
        seen: set[str] = set()
        for h in hits:
            vid = h["platform_item_id"]
            if vid not in seen:
                seen.add(vid)
                sources.append({
                    "platform_item_id": vid,
                    "title": h["title"],
                    "url": f"https://www.douyin.com/video/{vid}",
                    "score": round(h["score"], 4),
                })
        if route in ("db_content", "vector"):
            answer = self._ensure_sources(answer, sources)
        t_llm = time.perf_counter() - t0

        latency_ms = int((time.perf_counter() - started) * 1000)

        # Step 6: 持久化会话和消息
        session = (
            db.get(ChatSession, session_id) if session_id else None
        )
        if not session:
            title = normalized[:40] if normalized else "新对话"
            session = ChatSession(title=title)
            db.add(session)
            db.flush()

        retrieved_ids = sorted(
            {h["platform_item_id"] for h in hits}
        ) if hits else []
        retrieved_chunk_ids = (
            [h["chunk_id"] for h in hits] if hits else []
        )

        db.add(
            ChatMessage(
                session_id=session.id,
                role="user",
                content=query,
                route_type=route,
                retrieved_video_ids=json.dumps(retrieved_ids),
                retrieved_chunk_ids=json.dumps(retrieved_chunk_ids),
                model=settings.llm_model,
            )
        )
        db.add(
            ChatMessage(
                session_id=session.id,
                role="assistant",
                content=answer,
                route_type=route,
                retrieved_video_ids=json.dumps(retrieved_ids),
                retrieved_chunk_ids=json.dumps(retrieved_chunk_ids),
                model=settings.llm_model,
                latency_ms=latency_ms,
            )
        )
        db.commit()

        # 构建检索追踪信息
        trace = {
            "route": route,
            "steps": [
                {"name": "路由判断", "time_ms": int(t_route * 1000)},
                {"name": "向量检索", "time_ms": int(t_dense * 1000)},
                {"name": "上下文构建", "time_ms": int(t_ctx * 1000)},
                {"name": "LLM 生成", "time_ms": int(t_llm * 1000)},
            ],
            "chunks": [
                {
                    "chunk_id": h.get("chunk_id", ""),
                    "title": h.get("title", ""),
                    "text": (h.get("text", "") or "")[:200],
                    "score": round(h.get("score", 0), 4),
                }
                for h in hits[: settings.rag_context_count]
            ],
        }

        logger.info(
            "问答完成: route=%s, latency=%dms, hits=%d",
            route,
            latency_ms,
            len(hits),
        )
        return {
            "answer": answer,
            "sources": sources,
            "session_id": session.id,
            "route_type": route,
            "latency_ms": latency_ms,
            "trace": trace,
        }

    # ------------------------------------------------------------------
    # 流式回答
    # ------------------------------------------------------------------

    def answer_stream(
        self,
        db: Session,
        query: str,
        session_id: int | None,
        collection_id: str | None = None,
    ) -> Iterable[tuple[str, dict]]:
        """
        SSE 流式 RAG 问答

        先 yield sources 事件，再逐 token yield delta 事件，
        最后 yield done 事件（含 meta 信息）。

        :param db: 数据库会话
        :param query: 用户问题
        :param session_id: 会话 ID
        :yield: (event_name, payload) 元组
        """
        started = time.perf_counter()

        # Step 1-4 与非流式一致
        normalized = _normalize_query(query)
        chroma = get_chroma_service()
        has_data = chroma.count() > 0
        route = self._route(normalized, has_data)

        hits: list[dict] = []
        if route in ("vector", "db_content"):
            scope_ids: set[str] | None = None
            if collection_id and collection_id not in ("all", ""):
                scope_ids = self._resolve_collection_scope(db, collection_id)
            hits = self._dense_retrieve(normalized, scope_ids)

        context = self._truncate_context(
            self._build_context(route, hits, db, normalized)
        )
        history = self._history_context(db, session_id)
        system, user, is_structured = self._build_prompts(
            route, normalized, context, history
        )

        # 先发送 sources
        seen: set[str] = set()
        sources = []
        for h in hits:
            vid = h["platform_item_id"]
            if vid not in seen:
                seen.add(vid)
                sources.append({
                    "platform_item_id": vid,
                    "title": h["title"],
                    "url": f"https://www.douyin.com/video/{vid}",
                    "score": round(h["score"], 4),
                })
        yield ("sources", {"sources": sources})

        # Step 5: LLM 流式生成
        parts: list[str] = []
        try:
            for delta in llm_client.stream_chat(
                system_prompt=system, user_prompt=user
            ):
                if delta:
                    parts.append(delta)
                    yield ("delta", {"text": delta})

            answer = _sanitize_answer("".join(parts), is_structured)
            latency_ms = int((time.perf_counter() - started) * 1000)

            # Step 6: 持久化
            session = (
                db.get(ChatSession, session_id) if session_id else None
            )
            if not session:
                title = normalized[:40] if normalized else "新对话"
                session = ChatSession(title=title)
                db.add(session)
                db.flush()

            retrieved_ids = sorted(
                {h["platform_item_id"] for h in hits}
            ) if hits else []
            retrieved_chunk_ids = (
                [h["chunk_id"] for h in hits] if hits else []
            )

            db.add(
                ChatMessage(
                    session_id=session.id,
                    role="user",
                    content=query,
                    route_type=route,
                    retrieved_video_ids=json.dumps(retrieved_ids),
                    retrieved_chunk_ids=json.dumps(retrieved_chunk_ids),
                    model=settings.llm_model,
                )
            )
            db.add(
                ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=answer,
                    route_type=route,
                    retrieved_video_ids=json.dumps(retrieved_ids),
                    retrieved_chunk_ids=json.dumps(retrieved_chunk_ids),
                    model=settings.llm_model,
                    latency_ms=latency_ms,
                )
            )
            db.commit()

            logger.info(
                "流式问答完成: route=%s, latency=%dms, hits=%d",
                route,
                latency_ms,
                len(hits),
            )
            yield ("done", {"ok": True})
            yield (
                "meta",
                {
                    "session_id": session.id,
                    "route_type": route,
                    "latency_ms": latency_ms,
                    "sources": sources,
                },
            )

        except Exception as exc:
            db.rollback()
            logger.exception("流式问答失败")
            yield ("error", {"message": str(exc)})

    # ------------------------------------------------------------------
    # 会话管理
    # ------------------------------------------------------------------

    def list_sessions(self, db: Session, limit: int = 30) -> list[dict]:
        """
        获取会话列表

        :param db: 数据库会话
        :param limit: 最大返回数量
        :return: 会话列表
        """
        rows = (
            db.query(
                ChatSession,
                func.count(ChatMessage.id).label("message_count"),
                func.max(ChatMessage.created_at).label("last_message"),
            )
            .outerjoin(
                ChatMessage, ChatMessage.session_id == ChatSession.id
            )
            .group_by(ChatSession.id)
            .order_by(
                desc(func.max(ChatMessage.created_at)),
                desc(ChatSession.created_at),
            )
            .limit(limit)
            .all()
        )

        return [
            {
                "id": session.id,
                "title": session.title,
                "message_count": int(count or 0),
                "last_message_at": str(last_message) if last_message else None,
                "created_at": str(session.created_at),
            }
            for session, count, last_message in rows
        ]

    def get_messages(
        self, db: Session, session_id: int
    ) -> list[dict] | None:
        """
        获取会话消息历史

        :param db: 数据库会话
        :param session_id: 会话 ID
        :return: 消息列表，会话不存在返回 None
        """
        session = db.get(ChatSession, session_id)
        if session is None:
            return None

        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .all()
        )

        return [
            {
                "id": row.id,
                "session_id": row.session_id,
                "role": row.role,
                "content": row.content,
                "route_type": row.route_type,
                "created_at": str(row.created_at),
            }
            for row in rows
        ]

    def delete_session(self, db: Session, session_id: int) -> bool:
        """
        删除会话及其所有消息

        :param db: 数据库会话
        :param session_id: 会话 ID
        :return: 是否成功删除
        """
        session = db.get(ChatSession, session_id)
        if session is None:
            return False
        db.delete(session)
        db.commit()
        return True


# 全局单例
rag_service = RagService()
