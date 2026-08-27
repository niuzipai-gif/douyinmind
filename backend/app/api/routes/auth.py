"""
认证路由模块

提供抖音扫码登录、登录状态查询、退出登录等认证相关接口。
"""
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.douyin_collector import collector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/douyin", tags=["认证"])


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
