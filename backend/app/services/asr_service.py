"""
ASR 语音转写服务模块

使用 DashScope 云端 Paraformer 实时语音识别。
"""
from __future__ import annotations

import logging
from pathlib import Path

import dashscope
from dashscope.audio.asr import Recognition, RecognitionResult

from app.core.config import settings
from app.services.text_processing import RawSegment

logger = logging.getLogger(__name__)


class ASRService:
    """DashScope Paraformer 语音转写服务"""

    def __init__(self) -> None:
        dashscope.api_key = settings.dashscope_api_key

    def transcribe(self, audio_path: Path) -> tuple[list[RawSegment], str]:
        """
        将音频文件转写为文本段落

        :param audio_path: 音频文件路径（wav/mp3/m4a）
        :return: (转写段落列表, 语言代码)
        """
        logger.info("开始语音转写: %s (%d bytes)", audio_path.name, audio_path.stat().st_size)

        fmt = "wav" if audio_path.suffix.lower() in (".wav",) else "mp3"

        recognition = Recognition(
            model="paraformer-realtime-v2",
            format=fmt,
            sample_rate=16000,
            callback=None,
        )

        result: RecognitionResult = recognition.call(str(audio_path.resolve()))

        if result.status_code != 200:
            raise RuntimeError(
                f"ASR 转写失败 [{audio_path.name}]: "
                f"status={result.status_code}, message={result.message}"
            )

        segments: list[RawSegment] = []
        lang = "zh"

        output = result.output or {}
        sentences = output.get("sentence", [])
        if isinstance(sentences, dict):
            sentences = [sentences]
        if not isinstance(sentences, list):
            sentences = []

        for s in sentences:
            if not isinstance(s, dict):
                continue
            text = s.get("text", "").strip()
            if not text:
                continue
            segments.append(RawSegment(
                text=text,
                start_ms=int(s.get("begin_time", 0)),
                end_ms=int(s.get("end_time", 0)),
                lang=lang,
            ))

        logger.info("ASR 转写完成: %s, %d 段落", audio_path.name, len(segments))
        return segments, lang

    def transcribe_to_text(self, audio_path: Path) -> str:
        """将音频转写为纯文本"""
        segments, _ = self.transcribe(audio_path)
        if not segments:
            return ""
        return "\n".join(seg.text for seg in segments)


asr_service = ASRService()
