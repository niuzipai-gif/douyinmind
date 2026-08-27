"""
认证路由模块

提供抖音扫码登录、登录状态查询、退出登录等认证相关接口。
"""
import hmac
import logging
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.douyin_collector import collector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/douyin", tags=["认证"])


class LoginInput(BaseModel):
    action: Literal["move", "down", "up"]
    x: float = Field(ge=0, le=10000)
    y: float = Field(ge=0, le=10000)


class BridgeImportRequest(BaseModel):
    version: int = 1
    storage_state: dict[str, Any]
    collections: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []


@router.post("/login/start")
async def login_start():
    """
    启动抖音扫码登录

    后台启动 Playwright 浏览器打开抖音登录页，
    用户扫码后自动检测并保存登录态。

    :return: 启动结果（success + message）
    """
    success, message = collector.start_login()
    return {
        "success": success,
        "message": message,
        "status": collector.status,
    }


@router.get("/login/status")
async def login_status():
    """
    查询抖音登录状态

    :return: 当前状态（idle / pending / logged_in / failed）和描述信息
    """
    return {
        "status": collector.status,
        "message": collector.message,
    }


@router.get("/login/qr")
async def login_qr():
    """返回当前抖音登录页面截图，供前端显示二维码。"""
    image = collector.get_qr_image()
    if not image:
        raise HTTPException(status_code=404, detail="二维码尚未生成")
    return Response(
        content=image,
        media_type="image/png",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/login/input")
async def login_input(event: LoginInput):
    """转发前端在云端登录页面截图上的鼠标操作。"""
    accepted = collector.enqueue_login_input(event.action, event.x, event.y)
    if not accepted:
        raise HTTPException(status_code=409, detail="当前没有可交互的登录页面")
    return {"success": True}


@router.post("/bridge/import")
async def bridge_import(
    body: BridgeImportRequest,
    x_douyinmind_bridge_token: str = Header(default=""),
):
    """接收本机登录助手上传的抖音登录态和收藏快照。"""
    expected = settings.douyin_bridge_token
    if not expected or not hmac.compare_digest(
        x_douyinmind_bridge_token, expected
    ):
        raise HTTPException(status_code=403, detail="本机登录助手未授权")

    try:
        collector.import_bridge_payload(body.model_dump())
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"登录态导入失败: {exc}") from exc

    return {
        "success": True,
        "status": collector.status,
        "message": collector.message,
    }


@router.post("/logout")
async def logout():
    """
    退出抖音登录

    清理登录态文件、Playwright 用户数据、yt-dlp Cookie。

    :return: 退出结果
    """
    success, message = collector.logout()
    return {
        "success": success,
        "message": message,
        "status": collector.status,
    }
