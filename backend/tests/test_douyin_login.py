import pytest

from app.core.config import settings
from app.services.douyin_collector import DouyinCollector
from app.api.routes import auth
from app.services.douyin_collector import DouyinCollector


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
