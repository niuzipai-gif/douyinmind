"""
抖音采集服务模块

核心思路：登录后不关浏览器，在同一个持久化上下文中立即抓取数据，
抓完再关。避免 Cookie/Storage 跨 session 丢失的问题。

登录 → 检测到 Cookie → 立即调 Webpack API 抓收藏夹 → 存快照 → 关浏览器
同步 → 直接返回已缓存的快照（不重新打开浏览器）
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Optional

from playwright.sync_api import sync_playwright

from app.core.config import settings

logger = logging.getLogger(__name__)

LOGIN_COOKIE_POLL_INTERVAL = 1.0
LOGIN_SCREENSHOT_INTERVAL = 2.0


def _find_project_chromium_executable() -> Optional[Path]:
    """在 Playwright 浏览器目录中查找 Chromium"""
    base = Path(settings.playwright_browsers_path)
    if not base.exists():
        return None
    candidates = sorted(base.glob("chromium-*/chrome-win/chrome.exe"), reverse=True)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@dataclass
class FavoriteScrapedCollection:
    platform_collection_id: str
    title: str
    video_count: int
    cover_url: Optional[str] = None


@dataclass
class FavoriteScrapedVideo:
    platform_item_id: str
    url: str
    title: str
    author: str
    duration: Optional[int] = None
    collection_ids: set[str] = field(default_factory=set)


@dataclass
class FavoriteScrapeSnapshot:
    collections: list[FavoriteScrapedCollection] = field(default_factory=list)
    videos: list[FavoriteScrapedVideo] = field(default_factory=list)


class DouyinCollector:
    """抖音数据采集器 — 登录 + 抓取一体化"""

    def __init__(self) -> None:
        self.status: str = "idle"
        self.message: str = ""
        self._login_task: Optional[asyncio.Task] = None
        self.storage_state_path: Path = Path(settings.playwright_user_data_dir) / "state.json"
        self._snapshot: Optional[FavoriteScrapeSnapshot] = None
        self._qr_image: Optional[bytes] = None
        self._qr_lock = threading.Lock()
        self._login_input_queue: Queue[tuple[str, float, float]] = Queue()

    def set_qr_image(self, image: Optional[bytes]) -> None:
        """更新当前登录页面截图，供云端前端展示扫码二维码。"""
        with self._qr_lock:
            self._qr_image = bytes(image) if image else None

    def get_qr_image(self) -> Optional[bytes]:
        """返回当前登录页面截图；尚未生成时返回 None。"""
        with self._qr_lock:
            return self._qr_image

    def clear_qr_image(self) -> None:
        """清理登录二维码截图。"""
        self.set_qr_image(None)

    def export_bridge_payload(self) -> dict:
        """导出本机登录后的会话和收藏快照，供云端继续处理。"""
        if self._snapshot is None:
            raise RuntimeError("尚未完成本机登录和收藏夹抓取")

        if self.storage_state_path.exists():
            storage_state = json.loads(
                self.storage_state_path.read_text(encoding="utf-8")
            )
        else:
            storage_state = {"cookies": [], "origins": []}

        return {
            "version": 1,
            "storage_state": storage_state,
            "collections": [
                {
                    "platform_collection_id": item.platform_collection_id,
                    "title": item.title,
                    "video_count": item.video_count,
                    "cover_url": item.cover_url,
                }
                for item in self._snapshot.collections
            ],
            "videos": [
                {
                    "platform_item_id": item.platform_item_id,
                    "url": item.url,
                    "title": item.title,
                    "author": item.author,
                    "duration": item.duration,
                    "collection_ids": sorted(item.collection_ids),
                }
                for item in self._snapshot.videos
            ],
        }

    def import_bridge_payload(self, payload: dict) -> None:
        """导入本机登录态和快照，让云端继续执行同步/入库。"""
        storage_state = payload.get("storage_state")
        if not isinstance(storage_state, dict):
            raise ValueError("登录态格式无效")

        collections: list[FavoriteScrapedCollection] = []
        for item in payload.get("collections", []):
            if not isinstance(item, dict):
                continue
            collection_id = str(item.get("platform_collection_id") or "").strip()
            if not collection_id:
                continue
            collections.append(FavoriteScrapedCollection(
                platform_collection_id=collection_id,
                title=str(item.get("title") or "收藏夹")[:255],
                video_count=max(int(item.get("video_count") or 0), 0),
                cover_url=item.get("cover_url"),
            ))

        videos: list[FavoriteScrapedVideo] = []
        for item in payload.get("videos", []):
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("platform_item_id") or "").strip()
            url = str(item.get("url") or "").strip()
            if not item_id or not url:
                continue
            raw_ids = item.get("collection_ids") or []
            collection_ids = {
                str(collection_id).strip()
                for collection_id in raw_ids
                if str(collection_id).strip()
            }
            videos.append(FavoriteScrapedVideo(
                platform_item_id=item_id,
                url=url,
                title=str(item.get("title") or "Untitled")[:500],
                author=str(item.get("author") or "")[:255],
                duration=self._duration_to_seconds(item.get("duration")),
                collection_ids=collection_ids,
            ))

        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_state_path.write_text(
            json.dumps(storage_state, ensure_ascii=False), encoding="utf-8"
        )
        self._snapshot = FavoriteScrapeSnapshot(
            collections=collections,
            videos=videos,
        )
        self.status = "logged_in"
        self.message = f"本机登录成功，已同步 {len(collections)} 个收藏夹，{len(videos)} 个视频"
        self.clear_qr_image()

    def enqueue_login_input(self, action: str, x: float, y: float) -> bool:
        """把前端鼠标事件排队，避免跨线程直接操作 Playwright。"""
        if self.status != "pending" or action not in {"move", "down", "up"}:
            return False
        self._login_input_queue.put((action, float(x), float(y)))
        return True

    def apply_login_inputs(self, page) -> None:
        """在 Playwright 所在线程中执行前端传来的鼠标事件。"""
        while True:
            try:
                action, x, y = self._login_input_queue.get_nowait()
            except Empty:
                return
            if action == "move":
                page.mouse.move(x, y)
            elif action == "down":
                page.mouse.move(x, y)
                page.mouse.down()
            elif action == "up":
                page.mouse.move(x, y)
                page.mouse.up()

    # ------------------------------------------------------------------
    # 浏览器
    # ------------------------------------------------------------------

    def _browser_launch_kwargs(self) -> dict:
        """构建浏览器启动参数"""
        headless = bool(settings.playwright_headless)
        viewport = {"width": 900, "height": 900}
        executable = _find_project_chromium_executable()
        if executable:
            return {"headless": headless, "viewport": viewport, "executable_path": str(executable)}
        channel = settings.playwright_browser_channel.strip()
        if channel:
            return {"headless": headless, "viewport": viewport, "channel": channel}
        if sys.platform == "win32":
            return {"headless": headless, "viewport": viewport, "channel": "msedge"}
        return {"headless": headless, "viewport": viewport}

    def _capture_login_page(self, page) -> None:
        """保存当前登录页截图，让远端前端可以显示二维码。"""
        try:
            self.set_qr_image(page.screenshot(type="png"))
        except Exception as exc:
            logger.warning("登录二维码截图失败: %s", exc)

    # ------------------------------------------------------------------
    # 登录 + 同步抓取（在同一个浏览器会话中完成）
    # ------------------------------------------------------------------

    def start_login(self) -> tuple[bool, str]:
        """启动扫码登录（后台异步），登录成功后自动抓取收藏夹快照"""
        if self.status == "pending" and self._login_task and not self._login_task.done():
            return False, "登录已在进行中"
        self.status = "pending"
        self.message = "正在生成二维码，请稍候"
        self._snapshot = None
        self.clear_qr_image()
        self._login_task = asyncio.ensure_future(self._login_flow())
        return True, self.message

    async def _login_flow(self) -> None:
        await asyncio.to_thread(self._login_and_fetch_sync)

    def _login_and_fetch_sync(self) -> None:
        """
        在同一个持久化浏览器上下文中完成：登录检测 → 数据抓取

        关键：不关浏览器，登录后立即在同一个 session 中抓数据
        """
        try:
            with sync_playwright() as p:
                kwargs = self._browser_launch_kwargs()
                logger.info("启动登录浏览器: %s", kwargs)
                context = p.chromium.launch_persistent_context(
                    user_data_dir=settings.playwright_user_data_dir,
                    **kwargs,
                )
                page = context.pages[0] if context.pages else context.new_page()

                # 1. 等待扫码登录
                page.goto(settings.douyin_home_url, timeout=120_000)
                self._capture_login_page(page)
                self.message = "请用抖音 App 扫描二维码；如出现滑块验证，请在下方图片上拖动"
                logger.info("已打开抖音首页，等待扫码登录...")

                found = False
                deadline = time.monotonic() + 120
                last_capture = 0.0
                while time.monotonic() < deadline:
                    self.apply_login_inputs(page)
                    cookies = context.cookies()
                    has_login = any(
                        c.get("name") in {"sessionid", "sid_guard"} for c in cookies
                    )
                    if has_login:
                        found = True
                        break
                    now = time.monotonic()
                    if now - last_capture >= LOGIN_SCREENSHOT_INTERVAL:
                        self._capture_login_page(page)
                        last_capture = now
                    time.sleep(LOGIN_COOKIE_POLL_INTERVAL)

                if not found:
                    self.status = "failed"
                    self.message = "登录超时（120秒），请重试"
                    self.clear_qr_image()
                    context.close()
                    return

                logger.info("扫码登录成功，立即开始抓取收藏夹...")
                self.status = "logged_in"
                self.message = "登录成功，正在同步收藏夹..."
                self.clear_qr_image()

                # 2. 立即在同一个 context 中抓数据
                try:
                    snapshot = self._fetch_in_context(page)
                    self._snapshot = snapshot
                    self.status = "logged_in"
                    self.message = f"登录成功，已同步 {len(snapshot.collections)} 个收藏夹，{len(snapshot.videos)} 个视频"
                    logger.info("登录+抓取全部完成: %d 收藏夹, %d 视频", len(snapshot.collections), len(snapshot.videos))
                except Exception as exc:
                    logger.exception("抓取收藏夹失败")
                    self.status = "logged_in"
                    self.message = f"登录成功，但抓取失败: {str(exc)[:100]}"

                # 3. 保存登录态
                context.storage_state(path=str(self.storage_state_path))
                context.close()

        except Exception as exc:
            logger.exception("登录流程异常")
            self.status = "failed"
            self.message = str(exc)[:500]
            self.clear_qr_image()

    def _fetch_in_context(self, page) -> FavoriteScrapeSnapshot:
        """
        在已有的浏览器页面中通过 Webpack API 抓取收藏夹数据

        :param page: 已登录的 Playwright Page
        :return: 收藏夹快照
        """
        # 先回到首页确保 Webpack 已加载
        page.goto(settings.douyin_home_url, timeout=120_000, wait_until="domcontentloaded")
        time.sleep(3.0)

        # 检查 Webpack
        try:
            page.wait_for_function(
                "typeof window.webpackChunkdouyin_web !== 'undefined'",
                timeout=15000,
            )
            logger.info("Webpack 已就绪")
        except Exception:
            page.reload(wait_until="domcontentloaded", timeout=30000)
            time.sleep(4.0)
            try:
                page.wait_for_function(
                    "typeof window.webpackChunkdouyin_web !== 'undefined'",
                    timeout=15000,
                )
                logger.info("Webpack 刷新后就绪")
            except Exception:
                raise RuntimeError("抖音页面加载失败：Webpack 模块未检测到，请确认网络正常后重试")

        # 导航到收藏夹页面
        page.goto("https://www.douyin.com/user/self?showTab=favorite_collection",
                  timeout=120_000, wait_until="domcontentloaded")
        time.sleep(4.0)

        # 执行 JS 调用 Webpack collects 模块
        result = page.evaluate("""
            async () => {
                const chunks = window.webpackChunkdouyin_web;
                if (!Array.isArray(chunks)) return {ok:false, error:"no_webpack"};
                const req = chunks.push([[Symbol("c")], {}, r => r]);
                try { chunks.pop(); } catch(e) {}
                if (!req || !req.m) return {ok:false, error:"no_require"};

                let mid = null;
                for (const [id, mod] of Object.entries(req.m)) {
                    let src = "";
                    try { src = Function.prototype.toString.call(mod); } catch(e) { continue; }
                    if (src.includes("/aweme/v1/web/collects/list/") && src.includes("/aweme/v1/web/collects/video/list/")) {
                        mid = id; break;
                    }
                }
                if (!mid) return {ok:false, error:"module_not_found"};

                const api = req(Number(mid));

                // 智能查找 API 函数
                let listFn = null, videoFn = null;
                for (const key of Object.keys(api)) {
                    const v = api[key];
                    if (typeof v !== 'function') continue;
                    try {
                        const src = Function.prototype.toString.call(v);
                        if (!listFn && src.includes('collects/list')) listFn = v;
                        if (!videoFn && src.includes('collects/video/list')) videoFn = v;
                    } catch(e) {}
                }
                if (!listFn) listFn = api.So;
                if (!videoFn) videoFn = api.d6;
                if (typeof listFn !== "function" || typeof videoFn !== "function")
                    return {ok:false, error:"bad_exports", keys:Object.keys(api||{}).slice(0,20)};

                // 拉收藏夹列表
                const collections = [];
                let cursor = 0, guard = 0;
                while (guard < 30 && collections.length < 100) {
                    guard++;
                    const r = await listFn({cursor, offset:30});
                    if (!r || r.statusCode !== 0) {
                        return {ok:false, error:"list_status", statusCode:r?.statusCode, msg:r?.statusMsg};
                    }
                    for (const c of (Array.isArray(r.data) ? r.data : []))
                        if (c && c.collectionFolderId) collections.push(c);
                    cursor = Number(r.cursor || 0);
                    if (!r.hasMore) break;
                }

                // 拉每个收藏夹的视频
                const byCol = {};
                for (const c of collections) {
                    const cid = String(c.collectionFolderId);
                    const rows = [];
                    const seen = new Set();
                    let cCur = 0, cG = 0;
                    while (cG < 120 && rows.length < 500) {
                        cG++;
                        const vr = await videoFn({collectsId:cid, cursor:cCur, offset:20});
                        if (!vr || vr.statusCode !== 0) break;
                        for (const v of (Array.isArray(vr.data) ? vr.data : [])) {
                            const vid = String(v?.awemeId || v?.groupId || "").trim();
                            if (!vid || seen.has(vid)) continue;
                            seen.add(vid);
                            rows.push({
                                awemeId:vid,
                                title:String(v?.itemTitle||v?.desc||"Untitled"),
                                author:String(v?.authorInfo?.nickname||""),
                                durationMs:Number(v?.video?.duration||0)
                            });
                        }
                        cCur = Number(vr.cursor || 0);
                        if (!vr.hasMore) break;
                    }
                    byCol[cid] = rows;
                }
                return {ok:true, collections, itemsByCollection:byCol};
            }
        """)

        if not isinstance(result, dict) or not result.get("ok"):
            error = result.get("error", "unknown") if isinstance(result, dict) else str(result)
            raise RuntimeError(f"Webpack 模块调用失败: {error}")

        # 解析结果
        collections: list[FavoriteScrapedCollection] = []
        videos_by_id: dict[str, FavoriteScrapedVideo] = {}

        for col in (result.get("collections") or []):
            cid = str(col.get("collectionFolderId") or "").strip()
            if not cid:
                continue
            collections.append(FavoriteScrapedCollection(
                platform_collection_id=cid,
                title=str(col.get("collectionFolderName") or "收藏夹")[:255],
                video_count=max(int(col.get("videoTotal") or 0), 0),
                cover_url=col.get("cover"),
            ))
            rows = (result.get("itemsByCollection") or {}).get(cid, [])
            for row in (rows or []):
                aid = str(row.get("awemeId") or "").strip()
                if not aid or not aid.isdigit():
                    continue
                if aid not in videos_by_id:
                    videos_by_id[aid] = FavoriteScrapedVideo(
                        platform_item_id=aid,
                        url=f"https://www.douyin.com/video/{aid}",
                        title=str(row.get("title") or "Untitled")[:500],
                        author=str(row.get("author") or "").strip()[:255],
                        duration=self._duration_to_seconds(row.get("durationMs")),
                    )
                    videos_by_id[aid].collection_ids.add(cid)

        return FavoriteScrapeSnapshot(
            collections=collections,
            videos=list(videos_by_id.values()),
        )

    @staticmethod
    def _duration_to_seconds(raw) -> Optional[int]:
        if raw is None:
            return None
        try:
            d = int(raw)
        except (TypeError, ValueError):
            return None
        if d <= 0:
            return None
        return d // 1000 if d > 1000 else d

    # ------------------------------------------------------------------
    # 同步接口（返回缓存的快照）
    # ------------------------------------------------------------------

    async def fetch_snapshot(
        self, max_collections: int = 100, max_videos_per_collection: int = 500
    ) -> FavoriteScrapeSnapshot:
        """返回登录时已抓取的快照，如果不存在则报错"""
        if self._snapshot is None:
            raise RuntimeError("尚未登录或登录时未成功抓取，请先扫码登录")
        return self._snapshot

    # ------------------------------------------------------------------
    # 登出
    # ------------------------------------------------------------------

    def logout(self) -> tuple[bool, str]:
        if self._login_task and not self._login_task.done():
            self._login_task.cancel()
            self._login_task = None

        errors: list[str] = []
        try:
            if self.storage_state_path.exists():
                self.storage_state_path.unlink(missing_ok=True)
        except Exception as exc:
            errors.append(f"删除登录态失败: {exc}")

        user_data_dir = Path(settings.playwright_user_data_dir)
        try:
            if user_data_dir.exists():
                shutil.rmtree(user_data_dir, ignore_errors=False)
            user_data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            errors.append(f"清理用户数据失败: {exc}")

        self._snapshot = None
        self.clear_qr_image()
        if errors:
            self.status = "failed"
            self.message = "; ".join(errors)[:1000]
            return False, self.message

        self.status = "idle"
        self.message = "已退出登录"
        return True, self.message


# 全局单例
collector = DouyinCollector()
