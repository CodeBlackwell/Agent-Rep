"""
Mobile exhibits strip tests.

Covers: strip visibility per breakpoint, tile rendering, compact state
after hero-faded, bottom sheet open/close/dismiss, desktop hidden.
"""

import os
import pytest
from tests.e2e.conftest import (
    PHONE_DEVICES, ALL_MOBILE_DEVICES, CROSS_BROWSER_DEVICES,
    IPHONE_15, IPHONE_SE, PIXEL_7, IPAD_MINI, DESKTOP_CHROME,
    make_page, device_id, BASE_URL,
)

SCREENSHOTS = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOTS, exist_ok=True)


def _wait_for_strip(page, timeout=5000):
    """Wait for the strip to populate with tiles (repos fetched)."""
    page.wait_for_function(
        "document.querySelectorAll('.hero-strip__tile').length > 0",
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Strip visibility
# ---------------------------------------------------------------------------

class TestStripVisibility:
    """Strip should be visible on mobile, hidden on desktop."""

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_strip_visible_on_phones(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            display = page.evaluate(
                "window.getComputedStyle(document.getElementById('hero-exhibits')).display"
            )
            assert display == "flex", f"Strip should be flex on {device['name']}, got {display}"
        finally:
            page.close()
            ctx.close()

    def test_strip_visible_on_tablet(self):
        ctx, page = make_page(IPAD_MINI, BASE_URL)
        try:
            _wait_for_strip(page)
            display = page.evaluate(
                "window.getComputedStyle(document.getElementById('hero-exhibits')).display"
            )
            assert display == "flex", f"Strip should be flex on tablet, got {display}"
        finally:
            page.close()
            ctx.close()

    def test_strip_hidden_on_desktop(self):
        ctx, page = make_page(DESKTOP_CHROME, BASE_URL)
        try:
            page.wait_for_timeout(2000)
            display = page.evaluate(
                "window.getComputedStyle(document.getElementById('hero-exhibits')).display"
            )
            assert display == "none", f"Strip should be hidden on desktop, got {display}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Tile rendering
# ---------------------------------------------------------------------------

class TestTileRendering:
    """Tiles should have SVG rings and name labels."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_tiles_have_svg_rings(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            result = page.evaluate("""() => {
                const tiles = document.querySelectorAll('.hero-strip__tile');
                const svgCount = document.querySelectorAll('.hero-strip__tile svg').length;
                return { tiles: tiles.length, svgs: svgCount };
            }""")
            assert result["tiles"] > 0, "Should have at least one tile"
            assert result["svgs"] == result["tiles"], \
                f"Each tile needs an SVG ring: {result['svgs']} svgs for {result['tiles']} tiles"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_tiles_have_name_labels(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            names = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('.hero-strip__name'))
                    .map(el => el.textContent.trim());
            }""")
            assert len(names) > 0, "Should have name labels"
            assert all(len(n) > 0 for n in names), f"All labels should have text: {names}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", [IPHONE_SE, PIXEL_7], ids=device_id)
    def test_strip_scrollable(self, device):
        """Strip should have horizontal scroll when tiles overflow."""
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            result = page.evaluate("""() => {
                const strip = document.getElementById('hero-exhibits');
                return {
                    scrollWidth: strip.scrollWidth,
                    clientWidth: strip.clientWidth,
                };
            }""")
            assert result["scrollWidth"] >= result["clientWidth"], \
                "Strip should be at least as wide as its container (scrollable if overflows)"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Compact state after hero-faded
# ---------------------------------------------------------------------------

class TestCompactState:
    """Strip should shrink when hero-faded class is added."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_strip_compact_after_hero_fade(self, device):
        """After hero-faded, tiles should be at compact size (48px)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.evaluate("document.body.classList.add('hero-faded')")
            page.wait_for_timeout(600)
            compact_w = page.evaluate("""
                document.querySelector('.hero-strip__tile')?.getBoundingClientRect().width || 0
            """)
            assert compact_w <= 48, \
                f"Tile should be compact (<=48px), got {compact_w}"
        finally:
            page.close()
            ctx.close()

    def test_tablet_strip_shrinks_on_hero_fade(self):
        """Tablet starts full-size (76px) and should shrink to compact on hero-faded."""
        ctx, page = make_page(IPAD_MINI, BASE_URL)
        try:
            _wait_for_strip(page)
            initial_w = page.evaluate("""
                document.querySelector('.hero-strip__tile')?.getBoundingClientRect().width || 0
            """)
            page.evaluate("document.body.classList.add('hero-faded')")
            page.wait_for_timeout(600)
            compact_w = page.evaluate("""
                document.querySelector('.hero-strip__tile')?.getBoundingClientRect().width || 0
            """)
            assert compact_w < initial_w, \
                f"Tablet tile should shrink: initial={initial_w}, compact={compact_w}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_name_labels_hidden_when_compact(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.evaluate("document.body.classList.add('hero-faded')")
            page.wait_for_timeout(600)
            opacity = page.evaluate("""
                window.getComputedStyle(
                    document.querySelector('.hero-strip__name')
                ).opacity
            """)
            assert opacity == "0", f"Name labels should be hidden, got opacity={opacity}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Bottom sheet
# ---------------------------------------------------------------------------

class TestBottomSheet:
    """Tapping a tile should open a bottom sheet with repo detail."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_sheet_opens_on_tile_tap(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            page.wait_for_timeout(500)
            is_open = page.evaluate(
                "document.querySelector('.repo-sheet--open') !== null"
            )
            assert is_open, "Bottom sheet should open on tile tap"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_sheet_has_ring_and_title(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            page.wait_for_timeout(500)
            result = page.evaluate("""() => {
                const header = document.querySelector('.repo-sheet__header');
                return {
                    hasSvg: header?.querySelector('svg') !== null,
                    title: header?.querySelector('.repo-sheet__title')?.textContent || '',
                };
            }""")
            assert result["hasSvg"], "Sheet header should have an SVG ring"
            assert len(result["title"]) > 0, "Sheet header should have a title"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_sheet_loads_detail(self, device):
        """Sheet body should populate with repo detail after API call."""
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            # Wait for detail to load (replaces "Loading…")
            page.wait_for_function(
                "!document.querySelector('.repo-sheet__body')?.textContent.includes('Loading')",
                timeout=8000,
            )
            has_content = page.evaluate("""() => {
                const body = document.querySelector('.repo-sheet__body');
                return body && body.children.length > 0 &&
                    !body.textContent.includes('Loading');
            }""")
            assert has_content, "Sheet body should have loaded repo detail"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_sheet_closes_on_backdrop(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            page.wait_for_timeout(500)
            page.locator(".repo-sheet__backdrop").click(position={"x": 5, "y": 5})
            page.wait_for_timeout(500)
            is_open = page.evaluate(
                "document.querySelector('.repo-sheet--open') !== null"
            )
            assert not is_open, "Sheet should close on backdrop click"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_sheet_closes_on_escape(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            page.wait_for_timeout(500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            is_open = page.evaluate(
                "document.querySelector('.repo-sheet--open') !== null"
            )
            assert not is_open, "Sheet should close on Escape"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Screenshots — for visual verification
# ---------------------------------------------------------------------------

class TestScreenshots:
    """Capture screenshots at key states for visual review."""

    def test_iphone_se_initial(self):
        ctx, page = make_page(IPHONE_SE, BASE_URL)
        try:
            _wait_for_strip(page)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_iphone_se_initial.png"))
        finally:
            page.close()
            ctx.close()

    def test_iphone15_initial(self):
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            _wait_for_strip(page)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_iphone15_initial.png"))
        finally:
            page.close()
            ctx.close()

    def test_pixel7_initial(self):
        ctx, page = make_page(PIXEL_7, BASE_URL)
        try:
            _wait_for_strip(page)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_pixel7_initial.png"))
        finally:
            page.close()
            ctx.close()

    def test_ipad_initial(self):
        ctx, page = make_page(IPAD_MINI, BASE_URL)
        try:
            _wait_for_strip(page)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_ipad_initial.png"))
        finally:
            page.close()
            ctx.close()

    def test_desktop_no_strip(self):
        ctx, page = make_page(DESKTOP_CHROME, BASE_URL)
        try:
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_desktop_hidden.png"))
        finally:
            page.close()
            ctx.close()

    def test_iphone15_compact_state(self):
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            _wait_for_strip(page)
            page.evaluate("document.body.classList.add('hero-faded')")
            page.wait_for_timeout(600)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_iphone15_compact.png"))
        finally:
            page.close()
            ctx.close()

    def test_iphone15_sheet_open(self):
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            page.wait_for_function(
                "!document.querySelector('.repo-sheet__body')?.textContent.includes('Loading')",
                timeout=8000,
            )
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_iphone15_sheet.png"))
        finally:
            page.close()
            ctx.close()

    def test_pixel7_sheet_open(self):
        ctx, page = make_page(PIXEL_7, BASE_URL)
        try:
            _wait_for_strip(page)
            page.locator(".hero-strip__tile").first.click()
            page.wait_for_function(
                "!document.querySelector('.repo-sheet__body')?.textContent.includes('Loading')",
                timeout=8000,
            )
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SCREENSHOTS, "strip_pixel7_sheet.png"))
        finally:
            page.close()
            ctx.close()
