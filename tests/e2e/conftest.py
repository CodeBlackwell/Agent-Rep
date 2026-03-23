"""
E2E test fixtures for mobile cross-browser testing.

Targets localhost:7860 by default (fast). Set BASE_URL env var for production.
Start the dev server first: just dev
"""

import os
import pytest
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

# ---------------------------------------------------------------------------
# Target URL — localhost by default for speed
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("BASE_URL", "http://localhost:7860")

# ---------------------------------------------------------------------------
# Device configurations
# ---------------------------------------------------------------------------

IPHONE_15 = {
    "name": "iPhone 15",
    "viewport": {"width": 393, "height": 852},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "browser": "webkit",
}

IPHONE_15_PRO_MAX = {
    "name": "iPhone 15 Pro Max",
    "viewport": {"width": 430, "height": 932},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "browser": "webkit",
}

IPHONE_SE = {
    "name": "iPhone SE",
    "viewport": {"width": 375, "height": 667},
    "device_scale_factor": 2,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "browser": "webkit",
}

IPAD_MINI = {
    "name": "iPad Mini",
    "viewport": {"width": 768, "height": 1024},
    "device_scale_factor": 2,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    ),
    "browser": "webkit",
}

PIXEL_7 = {
    "name": "Pixel 7",
    "viewport": {"width": 412, "height": 915},
    "device_scale_factor": 2.625,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.6099.210 Mobile Safari/537.36"
    ),
    "browser": "chromium",
}

GALAXY_S23 = {
    "name": "Galaxy S23",
    "viewport": {"width": 360, "height": 780},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 14; SM-S911B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.6099.210 Mobile Safari/537.36"
    ),
    "browser": "chromium",
}

GALAXY_FOLD = {
    "name": "Galaxy Z Fold 5 (folded)",
    "viewport": {"width": 344, "height": 882},
    "device_scale_factor": 3,
    "is_mobile": True,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (Linux; Android 14; SM-F946B) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.6099.210 Mobile Safari/537.36"
    ),
    "browser": "chromium",
}

# Firefox mobile — is_mobile not supported by Playwright Firefox
FIREFOX_MOBILE = {
    "name": "Firefox Mobile",
    "viewport": {"width": 390, "height": 844},
    "device_scale_factor": 3,
    "is_mobile": False,
    "has_touch": True,
    "user_agent": (
        "Mozilla/5.0 (Android 14; Mobile; rv:121.0) "
        "Gecko/121.0 Firefox/121.0"
    ),
    "browser": "firefox",
}

DESKTOP_CHROME = {
    "name": "Desktop Chrome",
    "viewport": {"width": 1440, "height": 900},
    "device_scale_factor": 1,
    "is_mobile": False,
    "has_touch": False,
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.6099.210 Safari/537.36"
    ),
    "browser": "chromium",
}

# ---------------------------------------------------------------------------
# Device lists
# ---------------------------------------------------------------------------

ALL_MOBILE_DEVICES = [
    IPHONE_15, IPHONE_15_PRO_MAX, IPHONE_SE, IPAD_MINI,
    PIXEL_7, GALAXY_S23, GALAXY_FOLD, FIREFOX_MOBILE,
]

PHONE_DEVICES = [
    IPHONE_15, IPHONE_15_PRO_MAX, IPHONE_SE,
    PIXEL_7, GALAXY_S23, GALAXY_FOLD, FIREFOX_MOBILE,
]

IOS_DEVICES = [IPHONE_15, IPHONE_15_PRO_MAX, IPHONE_SE, IPAD_MINI]

CROSS_BROWSER_DEVICES = [IPHONE_15, PIXEL_7, FIREFOX_MOBILE]


def device_id(device: dict) -> str:
    return device["name"].lower().replace(" ", "-").replace("(", "").replace(")", "")


# ---------------------------------------------------------------------------
# Browser management — session-scoped, reused across all tests
# ---------------------------------------------------------------------------

_playwright = None
_browsers: dict[str, Browser] = {}
_unavailable_browsers: set[str] = set()


def _get_browser(browser_name: str) -> Browser:
    """Lazily launch browsers, skip if unavailable."""
    global _playwright
    if browser_name in _unavailable_browsers:
        pytest.skip(f"{browser_name} unavailable (missing system deps)")
    if _playwright is None:
        _playwright = sync_playwright().start()
    if browser_name not in _browsers:
        launcher = getattr(_playwright, browser_name)
        try:
            _browsers[browser_name] = launcher.launch(headless=True)
        except Exception as e:
            _unavailable_browsers.add(browser_name)
            pytest.skip(f"{browser_name} cannot launch: {e}")
    return _browsers[browser_name]


def _cleanup_browsers():
    global _playwright
    for b in _browsers.values():
        try:
            b.close()
        except Exception:
            pass
    _browsers.clear()
    if _playwright:
        _playwright.stop()
        _playwright = None


@pytest.fixture(scope="session", autouse=True)
def _browser_teardown():
    yield
    _cleanup_browsers()


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def base_url() -> str:
    return BASE_URL


def make_context(device: dict) -> BrowserContext:
    """Create a browser context for a device config."""
    browser = _get_browser(device["browser"])
    ctx_kwargs = {
        "viewport": device["viewport"],
        "device_scale_factor": device["device_scale_factor"],
        "has_touch": device["has_touch"],
        "user_agent": device["user_agent"],
    }
    if device["browser"] != "firefox":
        ctx_kwargs["is_mobile"] = device["is_mobile"]
    return browser.new_context(**ctx_kwargs)


def make_page(device: dict, url: str, wait_for_load: bool = True) -> tuple[BrowserContext, Page]:
    """Create context + page, navigate, wait for DOM ready.

    By default, forces the loading screen to complete immediately via JS
    instead of waiting for the 19MB background.svg to load.
    """
    ctx = make_context(device)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded")
    if wait_for_load:
        # Force-complete the loading sequence instead of waiting for bg image
        page.evaluate("""() => {
            document.body.classList.remove('is-loading');
            document.body.classList.add('is-reveal', 'is-loaded');
            const loader = document.getElementById('loader');
            if (loader) loader.remove();
        }""")
        # Give a tick for CSS transitions/reflows to settle
        page.wait_for_timeout(100)
    return ctx, page


# ---------------------------------------------------------------------------
# Class-scoped device fixtures — ONE page load per test class per device
# ---------------------------------------------------------------------------

def _make_class_fixture(device_config):
    """Factory: create a class-scoped fixture for a device.
    The page is loaded once and shared across all tests in the class.
    Each test gets a fresh navigation to the same URL."""

    @pytest.fixture(scope="class")
    def _fixture(request):
        ctx, page = make_page(device_config, BASE_URL)
        request.cls._ctx = ctx
        request.cls._page = page
        yield page
        page.close()
        ctx.close()

    return _fixture


# Pre-built class fixtures for common devices
iphone15_shared = _make_class_fixture(IPHONE_15)
pixel7_shared = _make_class_fixture(PIXEL_7)
firefox_shared = _make_class_fixture(FIREFOX_MOBILE)
desktop_shared = _make_class_fixture(DESKTOP_CHROME)


# ---------------------------------------------------------------------------
# Per-test fixtures (fresh page each time — for tests that mutate state)
# ---------------------------------------------------------------------------

@pytest.fixture()
def iphone15_page(base_url):
    ctx, page = make_page(IPHONE_15, base_url)
    yield page
    page.close()
    ctx.close()


@pytest.fixture()
def pixel7_page(base_url):
    ctx, page = make_page(PIXEL_7, base_url)
    yield page
    page.close()
    ctx.close()


@pytest.fixture()
def desktop_page(base_url):
    ctx, page = make_page(DESKTOP_CHROME, base_url)
    yield page
    page.close()
    ctx.close()


@pytest.fixture()
def firefox_mobile_page(base_url):
    ctx, page = make_page(FIREFOX_MOBILE, base_url)
    yield page
    page.close()
    ctx.close()
