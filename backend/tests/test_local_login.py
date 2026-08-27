from __future__ import annotations

import pytest

from app.local_login import LocalLoginAlreadyRunning, SingleInstanceLock
from app.services.douyin_collector import (
    DouyinCollector,
    LOGIN_COOKIE_POLL_INTERVAL,
    LOGIN_SCREENSHOT_INTERVAL,
)


def test_local_login_lock_rejects_a_second_helper(tmp_path):
    lock_path = tmp_path / "douyinmind-login.lock"
    first = SingleInstanceLock(lock_path)
    first.acquire()
    try:
        with pytest.raises(LocalLoginAlreadyRunning):
            SingleInstanceLock(lock_path).acquire()
    finally:
        first.release()


def test_login_waiting_is_throttled_to_protect_cpu():
    assert LOGIN_COOKIE_POLL_INTERVAL >= 0.5
    assert LOGIN_SCREENSHOT_INTERVAL >= 1.0


def test_local_helper_can_disable_remote_screenshots():
    collector = DouyinCollector(capture_login_screenshots=False)
    assert collector._capture_login_screenshots is False
