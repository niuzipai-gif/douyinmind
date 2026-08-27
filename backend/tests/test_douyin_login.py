import pytest

from app.core.config import settings
from app.services.douyin_collector import (
    DouyinCollector,
    FavoriteScrapeSnapshot,
    FavoriteScrapedCollection,
    FavoriteScrapedVideo,
)
from app.api.routes import auth


class FakeMouse:
    def __init__(self):
        self.events = []

    def move(self, x, y):
        self.events.append(("move", x, y))

    def down(self):
        self.events.append(("down",))

    def up(self):
        self.events.append(("up",))


class FakePage:
    def __init__(self):
        self.mouse = FakeMouse()


def test_browser_launch_respects_headless_setting(monkeypatch):
    monkeypatch.setattr(settings, "playwright_headless", True)

    launch_kwargs = DouyinCollector()._browser_launch_kwargs()

    assert launch_kwargs["headless"] is True


def test_qr_image_can_be_read_and_cleared():
    collector = DouyinCollector()

    assert collector.get_qr_image() is None
    collector.set_qr_image(b"fake-png")
    assert collector.get_qr_image() == b"fake-png"

    collector.clear_qr_image()
    assert collector.get_qr_image() is None


def test_login_mouse_events_are_applied_in_order():
    collector = DouyinCollector()
    collector.status = "pending"
    page = FakePage()

    assert collector.enqueue_login_input("move", 10, 20)
    assert collector.enqueue_login_input("down", 10, 20)
    assert collector.enqueue_login_input("move", 80, 20)
    assert collector.enqueue_login_input("up", 80, 20)

    collector.apply_login_inputs(page)

    assert page.mouse.events == [
        ("move", 10, 20),
        ("move", 10, 20),
        ("down",),
        ("move", 80, 20),
        ("move", 80, 20),
        ("up",),
    ]


def test_local_login_payload_round_trips_to_cloud_collector(tmp_path):
    source = DouyinCollector()
    source.storage_state_path = tmp_path / "source" / "state.json"
    source.storage_state_path.parent.mkdir(parents=True)
    source.storage_state_path.write_text(
        '{"cookies":[{"name":"sessionid","value":"local-only"}]}',
        encoding="utf-8",
    )
    source._snapshot = FavoriteScrapeSnapshot(
        collections=[FavoriteScrapedCollection("c1", "知识", 1)],
        videos=[FavoriteScrapedVideo("v1", "https://www.douyin.com/video/v1", "标题", "作者", collection_ids={"c1"})],
    )

    payload = source.export_bridge_payload()

    target = DouyinCollector()
    target.storage_state_path = tmp_path / "target" / "state.json"
    target.import_bridge_payload(payload)

    assert target.status == "logged_in"
    assert target._snapshot is not None
    assert target._snapshot.videos[0].platform_item_id == "v1"
    assert target.storage_state_path.exists()

@pytest.mark.asyncio
async def test_login_qr_returns_png_response(monkeypatch):
    collector = DouyinCollector()
    collector.set_qr_image(b"fake-png")
    monkeypatch.setattr(auth, "collector", collector)

    response = await auth.login_qr()

    assert response.media_type == "image/png"
    assert response.body == b"fake-png"


@pytest.mark.asyncio
async def test_login_qr_returns_not_found_before_browser_is_ready(monkeypatch):
    monkeypatch.setattr(auth, "collector", DouyinCollector())

    with pytest.raises(auth.HTTPException) as error:
        await auth.login_qr()

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_bridge_import_requires_internal_token(monkeypatch):
    monkeypatch.setattr(settings, "douyin_bridge_token", "bridge-secret")
    body = auth.BridgeImportRequest(storage_state={"cookies": []})

    with pytest.raises(auth.HTTPException) as error:
        await auth.bridge_import(body, "wrong-secret")

    assert error.value.status_code == 403
