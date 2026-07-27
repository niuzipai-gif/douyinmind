"""
媒体下载服务模块

负责下载抖音视频的音频流：
1. 优先方案：yt-dlp 直接下载（使用 Playwright 登录态 Cookie）
2. 处理：ffmpeg 提取音频并转码为 mp3
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL

from app.core.config import settings

logger = logging.getLogger(__name__)

# 抖音请求头
DOUYIN_REFERER = "https://www.douyin.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class MediaPipelineError(RuntimeError):
    """媒体处理异常"""
    pass


def _resolve_ffmpeg_path() -> str:
    """
    查找 ffmpeg 可执行文件路径

    依次尝试：
    1. PATH 环境变量
    2. Windows 常见安装路径

    :return: ffmpeg 可执行文件路径
    :raises MediaPipelineError: 未找到 ffmpeg
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    common_paths = [
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for candidate in common_paths:
        if candidate.exists():
            return str(candidate)

    raise MediaPipelineError(
        "未找到 ffmpeg。请安装 ffmpeg 并加入 PATH，"
        "或将其路径添加到系统环境变量中。"
        "下载地址：https://www.gyan.dev/ffmpeg/builds/"
    )


def _export_cookiefile() -> Path:
    """
    从 Playwright 登录态导出 yt-dlp 格式的 Cookie 文件

    :return: Cookie 文件路径
    :raises MediaPipelineError: 登录态文件不存在
    """
    state_path = Path(settings.playwright_user_data_dir) / "state.json"
    if not state_path.exists():
        raise MediaPipelineError(
            "未找到登录状态文件，请先扫码登录抖音"
        )

    with state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)

    cookies = state.get("cookies", []) if isinstance(state, dict) else []
    cookie_dir = Path(settings.audio_cache_dir)
    cookie_dir.mkdir(parents=True, exist_ok=True)
    cookie_file = cookie_dir / "douyin_cookies.txt"

    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated from Playwright storage state",
    ]
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain") or "").strip()
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        if not domain or not name:
            continue

        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(cookie.get("path") or "/")
        secure = "TRUE" if bool(cookie.get("secure")) else "FALSE"
        expires_raw = cookie.get("expires")
        try:
            expires = (
                int(float(expires_raw))
                if expires_raw and float(expires_raw) > 0
                else 0
            )
        except (TypeError, ValueError):
            expires = 0

        lines.append(
            "\t".join([
                domain,
                include_subdomains,
                path,
                secure,
                str(expires),
                name,
                value,
            ])
        )

    cookie_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("已导出 Cookie 文件: %s", cookie_file)
    return cookie_file


def download_audio(
    video_url: str, platform_item_id: str
) -> Path:
    """
    下载抖音视频的音频流

    使用 yt-dlp 下载最佳音频流，通过 ffmpeg 后处理提取为 mp3。
    抖音视频自动使用 Playwright 登录态 Cookie 绕过鉴权。

    :param video_url: 视频页面 URL（如 https://www.douyin.com/video/xxx）
    :param platform_item_id: 抖音视频 ID
    :return: 下载后的音频文件路径
    :raises MediaPipelineError: 下载或转码失败
    """
    audio_dir = Path(settings.audio_cache_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(audio_dir / f"{platform_item_id}.%(ext)s")

    # yt-dlp 配置
    options: dict = {
        "outtmpl": output_template,
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }
        ],
        "retries": 3,
        "ffmpeg_location": _resolve_ffmpeg_path(),
    }

    # 抖音视频使用 Cookie
    if "douyin.com" in video_url:
        try:
            options["cookiefile"] = str(_export_cookiefile())
        except MediaPipelineError:
            logger.warning("无法导出 Cookie，尝试无 Cookie 下载")
        options["http_headers"] = {
            "Referer": DOUYIN_REFERER,
            "User-Agent": USER_AGENT,
        }

    logger.info("开始下载音频: %s", platform_item_id)
    try:
        with YoutubeDL(options) as ydl:
            ydl.extract_info(video_url, download=True)
    except Exception as exc:
        raise MediaPipelineError(
            f"音频下载失败 [{platform_item_id}]: {exc}"
        ) from exc

    # 查找下载的文件
    audio_path = audio_dir / f"{platform_item_id}.mp3"
    if not audio_path.exists():
        matches = sorted(audio_dir.glob(f"{platform_item_id}.*"))
        if not matches:
            raise MediaPipelineError(
                f"未找到下载的音频文件: {platform_item_id}"
            )
        audio_path = matches[0]

    # 用 ffmpeg 转码为 16kHz 单声道 WAV（DashScope 兼容格式）
    wav_path = audio_dir / f"{platform_item_id}.wav"
    ffmpeg = _resolve_ffmpeg_path()
    cmd = [
        ffmpeg, "-y", "-i", str(audio_path),
        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("ffmpeg 转码 WAV 失败: %s，回退原始文件", result.stderr[:200])
        return audio_path

    # 删除原始文件，返回 WAV
    try:
        audio_path.unlink(missing_ok=True)
    except Exception:
        pass

    logger.info("音频下载+转码完成: %s (%d bytes)", platform_item_id, wav_path.stat().st_size)
    return wav_path
