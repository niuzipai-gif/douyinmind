"""
日志配置模块

基于 loguru 的统一日志管理。
移除默认 handler，添加控制台输出和文件滚动日志。
"""
import sys

from loguru import logger


def setup_logging() -> None:
    """
    初始化日志配置

    配置内容：
    - 移除 loguru 默认 handler
    - 控制台输出：彩色格式，INFO 级别
    - 文件滚动日志：保留最近 7 天，ERROR 级别单独记录
    """
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level="INFO",
        colorize=True,
    )

    # 文件日志 — 全量
    logger.add(
        "logs/douyinrag_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
    )

    # 文件日志 — 仅 ERROR
    logger.add(
        "logs/error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="ERROR",
    )

    logger.info("日志系统初始化完成")
