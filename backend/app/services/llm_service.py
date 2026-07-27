"""
LLM 与 Embedding 客户端模块

封装两个上游服务：
1. DeepSeek（OpenAI 兼容协议）—— LLM 对话 + 流式输出
2. DashScope —— 文本向量化（Embedding）
"""
from __future__ import annotations

import logging
import time
from typing import Iterable, Sequence

import dashscope
from dashscope import TextEmbedding
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    LLM 客户端

    使用 DeepSeek API（兼容 OpenAI 协议）。
    支持普通对话和流式输出。
    """

    def __init__(self) -> None:
        """
        初始化 DeepSeek 客户端
        """
        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.llm_base_url,
        )

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> str:
        """
        发送非流式对话请求

        :param system_prompt: 系统提示词
        :param user_prompt: 用户消息
        :param temperature: 温度参数（0-2）
        :param max_tokens: 最大输出 Token 数
        :param timeout: 超时时间（秒）
        :return: LLM 生成的完整回复
        """
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=settings.llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "LLM chat 完成 (%sms, model=%s)", elapsed_ms, settings.llm_model
        )
        return response.choices[0].message.content or ""

    def stream_chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.6,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> Iterable[str]:
        """
        发送流式对话请求

        逐 token 返回生成内容，适合 SSE 推送给前端。

        :param system_prompt: 系统提示词
        :param user_prompt: 用户消息
        :param temperature: 温度参数
        :param max_tokens: 最大输出 Token 数
        :param timeout: 超时时间（秒）
        :yield: 每次生成的一小段文本
        """
        started = time.perf_counter()
        stream = self._client.chat.completions.create(
            model=settings.llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "LLM stream 完成 (%sms, model=%s)",
            elapsed_ms,
            settings.llm_model,
        )


class EmbeddingClient:
    """
    Embedding 客户端

    使用 DashScope TextEmbedding API。
    """

    def __init__(self) -> None:
        """
        初始化 DashScope Embedding 客户端
        """
        dashscope.api_key = settings.dashscope_api_key

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """
        将文本列表转换为向量

        :param texts: 待向量化的文本列表
        :return: 对应的向量列表，每个向量为 float 列表
        :raises RuntimeError: API Key 未配置或调用失败
        """
        if not texts:
            return []

        texts = list(texts)
        started = time.perf_counter()

        resp = TextEmbedding.call(
            model=settings.embedding_model,
            input=texts,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Embedding 调用失败: status={resp.status_code}, "
                f"message={resp.message}"
            )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Embedding 完成: %d texts, %dms, model=%s",
            len(texts),
            elapsed_ms,
            settings.embedding_model,
        )

        # 按输入顺序返回向量
        embeddings = []
        for item in resp.output.get("embeddings", []):
            embeddings.append(item["embedding"])
        return embeddings

    def embed_text(self, text: str) -> list[float]:
        """
        将单条文本转换为向量

        :param text: 待向量化的文本
        :return: 向量
        """
        return self.embed_texts([text])[0]


# 全局单例
llm_client = LLMClient()
embedding_client = EmbeddingClient()
