"""本机抖音登录助手。

在用户自己的电脑上打开可见 Chromium 完成扫码和风控验证，
再把登录态与收藏快照通过内部口令上传到 Render。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.douyin_collector import DouyinCollector


DEFAULT_CLOUD_URL = "https://douyinmind-backend.onrender.com"


class LocalLoginAlreadyRunning(RuntimeError):
    """已有一个本机登录助手在运行。"""


class SingleInstanceLock:
    """用操作系统文件锁保证本机登录助手只有一个实例。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="ascii")
        handle.seek(0)
        handle.write("1")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise LocalLoginAlreadyRunning from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def main() -> int:
    parser = argparse.ArgumentParser(description="DouyinMind 本机抖音登录助手")
    parser.add_argument(
        "--cloud-url",
        default=DEFAULT_CLOUD_URL,
        help="Render 后端地址",
    )
    parser.add_argument(
        "--bridge-token",
        default=settings.douyin_bridge_token,
        help="本机助手与云端之间的内部口令，默认读取 backend/.env",
    )
    args = parser.parse_args()

    if not args.bridge_token:
        print("未配置 DOUYIN_BRIDGE_TOKEN，请先填写 backend/.env。", file=sys.stderr)
        return 2

    try:
        with SingleInstanceLock(
            Path(settings.playwright_user_data_dir).parent / "local_login.lock"
        ):
            collector = DouyinCollector()
            print("即将打开本机抖音登录窗口，请扫码并按提示完成验证。")
            collector._login_and_fetch_sync()

            if collector.status != "logged_in":
                print(f"本机登录失败：{collector.message}", file=sys.stderr)
                return 1

            payload = collector.export_bridge_payload()
            endpoint = f"{args.cloud_url.rstrip('/')}/api/auth/douyin/bridge/import"
            try:
                response = httpx.post(
                    endpoint,
                    headers={"X-DouyinMind-Bridge-Token": args.bridge_token},
                    json=payload,
                    timeout=180,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"上传到云端失败：{exc}", file=sys.stderr)
                return 1

            result = response.json()
            if not result.get("success"):
                print(f"云端导入失败：{result}", file=sys.stderr)
                return 1

            print("登录态和收藏夹快照已上传到云端。现在可以回到 GitHub Pages 使用。")
            return 0
    except LocalLoginAlreadyRunning:
        print("本机登录助手已经在运行，请直接使用已打开的登录窗口。", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
