"""
应用配置模块

基于 Pydantic Settings 的环境变量管理。
所有配置项从 .env 文件和环境变量读取，提供类型验证和默认值。
"""
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    应用全局配置

    配置优先级：环境变量 > .env 文件 > 默认值
    """

    # ===== API Key =====
    deepseek_api_key: str = ""
    """DeepSeek API Key，用于 LLM 对话"""

    dashscope_api_key: str = ""
    """DashScope API Key，用于 ASR 语音转写和 Embedding 向量化"""

    # ===== LLM 配置 =====
    llm_model: str = "deepseek-chat"
    """LLM 模型名称"""

    llm_base_url: str = "https://api.deepseek.com"
    """LLM API 地址，兼容 OpenAI 协议"""

    # ===== Embedding 配置 =====
    embedding_model: str = "text-embedding-v4"
    """DashScope Embedding 模型名称"""

    # ===== ASR 配置 =====
    asr_model: str = "paraformer-v2"
    """DashScope 语音识别模型"""

    # ===== 检索参数 =====
    retrieval_top_k: int = 8
    """最终返回的检索结果数量"""

    retrieval_mmr_fetch_k: int = 32
    """MMR 检索的候选池大小"""

    retrieval_mmr_lambda: float = 0.55
    """MMR 多样性系数（0=最大多样性，1=最大相关性）"""

    rag_context_count: int = 5
    """注入 LLM 的上下文 chunk 数量"""

    rag_prompt_max_context_chars: int = 8000
    """注入 LLM 的上下文最大字符数，超出截断"""

    # ===== 切块参数 =====
    chunk_size: int = 1000
    """文本切块大小（字符数）"""

    chunk_overlap: int = 200
    """相邻文本块重叠字符数"""

    # ===== 对话 =====
    chat_history_window: int = 6
    """注入上下文的历史消息数量（最近 N 条）"""

    chat_max_content_chars: int = 2000
    """单条历史消息最大字符数"""

    # ===== 数据库 =====
    database_url: str = "sqlite:///app/storage/douyinrag.db"
    """SQLite 数据库连接 URL"""

    chroma_persist_dir: str = "app/storage/chroma"
    """ChromaDB 向量库持久化目录"""

    # ===== 音频缓存 =====
    audio_cache_dir: str = "app/storage/audio_cache"
    """音频下载缓存目录"""

    # ===== Playwright / 抖音采集 =====
    playwright_headless: bool = False
    """Playwright 是否无头模式（登录时需要可见浏览器扫码）"""

    playwright_user_data_dir: str = "app/storage/playwright_user_data"
    """Playwright 持久化用户数据目录（保存登录状态）"""

    playwright_browsers_path: str = "app/storage/playwright_browsers"
    """Playwright 浏览器安装路径"""

    playwright_browser_channel: str = "chromium"
    """Playwright 浏览器渠道（chromium / msedge）"""

    douyin_home_url: str = "https://www.douyin.com"
    """抖音首页 URL"""

    douyin_favorites_url: str = "https://www.douyin.com/user/self?from_login=1"
    """抖音收藏夹页面 URL"""

    # ===== 项目路径 =====
    @property
    def project_root(self) -> Path:
        """
        获取项目根目录（backend/ 的上级目录）

        :return: 项目根目录的 Path 对象
        """
        return Path(__file__).resolve().parent.parent

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


# 全局单例
settings = Settings()
