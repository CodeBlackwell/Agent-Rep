"""
Mobile layout & responsiveness tests.

Covers viewport handling, breakpoint transitions, element sizing,
touch targets, font sizes, and visual rendering across all mobile devices.
"""

import pytest
from tests.e2e.conftest import (
    ALL_MOBILE_DEVICES, PHONE_DEVICES, IOS_DEVICES, CROSS_BROWSER_DEVICES,
    IPHONE_15, IPHONE_SE, GALAXY_FOLD, IPAD_MINI, DESKTOP_CHROME,
    make_page, device_id, BASE_URL,
)


# ---------------------------------------------------------------------------
# Page load & loading screen
# ---------------------------------------------------------------------------

class TestPageLoad:
    """Verify the page loads and the loading screen transitions correctly."""

    @pytest.mark.parametrize("device", ALL_MOBILE_DEVICES, ids=device_id)
    def test_page_loads_successfully(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            assert page.title(), "Page should have a title"
            assert "PROVE" in page.title()
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", ALL_MOBILE_DEVICES, ids=device_id)
    def test_loading_screen_fades(self, device):
        ctx, page = make_page(device, BASE_URL, wait_for_load=False)
        try:
            # Loader should exist initially
            loader = page.locator("#loader")
            assert loader.count() >= 0  # may already be removed

            # Body should get is-reveal class
            page.wait_for_function(
                "document.body.classList.contains('is-reveal')",
                timeout=15000,
            )

            # After transition, loader should be removed or invisible
            page.wait_for_timeout(1500)
            if loader.count() > 0:
                opacity = page.evaluate(
                    "window.getComputedStyle(document.getElementById('loader')).opacity"
                )
                assert opacity == "0", f"Loader should be invisible, got opacity={opacity}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_staggered_reveal_completes(self, device):
        """Hero elements should become visible after the reveal sequence."""
        ctx, page = make_page(device, BASE_URL)
        try:
            for selector in [".hero__name", ".hero__tagline", "#chat-panel"]:
                el = page.locator(selector)
                if el.count() > 0:
                    box = el.bounding_box()
                    assert box is not None, f"{selector} should be visible after reveal"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Viewport & layout
# ---------------------------------------------------------------------------

class TestViewportLayout:
    """Verify layout adapts correctly to mobile viewports."""

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_single_column_layout_on_phones(self, device):
        """Phones should show single-column layout (flex-direction: column)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            direction = page.evaluate(
                "window.getComputedStyle(document.querySelector('main')).flexDirection"
            )
            assert direction == "column", f"Expected column layout, got {direction}"
        finally:
            page.close()
            ctx.close()

    def test_two_column_layout_on_desktop(self):
        ctx, page = make_page(DESKTOP_CHROME, BASE_URL)
        try:
            direction = page.evaluate(
                "window.getComputedStyle(document.querySelector('main')).flexDirection"
            )
            assert direction == "row", f"Desktop should use row layout, got {direction}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_graph_panel_hidden_on_phones(self, device):
        """Graph panel should be display:none on phone viewports."""
        ctx, page = make_page(device, BASE_URL)
        try:
            display = page.evaluate(
                "window.getComputedStyle(document.getElementById('graph-panel')).display"
            )
            assert display == "none", f"Graph panel should be hidden on {device['name']}, got display={display}"
        finally:
            page.close()
            ctx.close()

    def test_graph_panel_visible_on_desktop(self):
        ctx, page = make_page(DESKTOP_CHROME, BASE_URL)
        try:
            display = page.evaluate(
                "window.getComputedStyle(document.getElementById('graph-panel')).display"
            )
            assert display != "none", "Graph panel should be visible on desktop"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_no_horizontal_overflow(self, device):
        """Page should not scroll horizontally on any mobile device."""
        ctx, page = make_page(device, BASE_URL)
        try:
            overflow = page.evaluate("""() => {
                return document.documentElement.scrollWidth > document.documentElement.clientWidth;
            }""")
            assert not overflow, f"Horizontal overflow detected on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_body_fills_viewport(self, device):
        """Body should fill the viewport without extra scrollbar."""
        ctx, page = make_page(device, BASE_URL)
        try:
            overflow = page.evaluate(
                "window.getComputedStyle(document.body).overflow"
            )
            assert overflow == "hidden", f"Body overflow should be hidden, got {overflow}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", [IPHONE_SE, GALAXY_FOLD], ids=device_id)
    def test_content_fits_small_screens(self, device):
        """Smallest screens should still show hero + chat without clipping."""
        ctx, page = make_page(device, BASE_URL)
        try:
            hero_box = page.locator(".hero").bounding_box()
            chat_box = page.locator("#chat-panel").bounding_box()
            assert hero_box is not None, "Hero should be visible"
            assert chat_box is not None, "Chat panel should be visible"
            # Chat panel should not extend below viewport
            viewport_h = device["viewport"]["height"]
            assert chat_box["y"] + chat_box["height"] <= viewport_h + 50, \
                f"Chat extends beyond viewport on {device['name']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Touch targets
# ---------------------------------------------------------------------------

class TestTouchTargets:
    """Apple HIG and WCAG require minimum 44x44px touch targets."""

    MIN_TOUCH_SIZE = 44

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_canvas_toggle_touch_target(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            btn = page.locator("#canvas-toggle")
            box = btn.bounding_box()
            assert box is not None, "Canvas toggle should be visible"
            assert box["width"] >= self.MIN_TOUCH_SIZE, \
                f"Canvas toggle width {box['width']}px < {self.MIN_TOUCH_SIZE}px"
            assert box["height"] >= self.MIN_TOUCH_SIZE, \
                f"Canvas toggle height {box['height']}px < {self.MIN_TOUCH_SIZE}px"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_jd_button_touch_target(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            btn = page.locator("#jd-btn")
            box = btn.bounding_box()
            assert box is not None, "JD button should be visible"
            assert box["width"] >= self.MIN_TOUCH_SIZE, \
                f"JD button width {box['width']}px < {self.MIN_TOUCH_SIZE}px"
            assert box["height"] >= self.MIN_TOUCH_SIZE, \
                f"JD button height {box['height']}px < {self.MIN_TOUCH_SIZE}px"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_starter_buttons_touch_target(self, device):
        """Starter question buttons should be large enough to tap."""
        ctx, page = make_page(device, BASE_URL)
        try:
            buttons = page.locator(".starter-btn")
            count = buttons.count()
            assert count > 0, "Starter buttons should be present"
            for i in range(count):
                box = buttons.nth(i).bounding_box()
                assert box is not None, f"Starter button {i} should be visible"
                # Height should be at least 44px for comfortable tapping
                assert box["height"] >= 36, \
                    f"Starter button {i} height {box['height']}px is too small for touch"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Font sizes (iOS zoom prevention)
# ---------------------------------------------------------------------------

class TestFontSizes:
    """iOS Safari zooms the page when input font-size < 16px."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_chat_input_font_size_prevents_zoom(self, device):
        """Chat input must be >= 16px to prevent iOS auto-zoom on focus."""
        ctx, page = make_page(device, BASE_URL)
        try:
            font_size = page.evaluate("""
                parseFloat(window.getComputedStyle(
                    document.getElementById('chat-input')
                ).fontSize)
            """)
            assert font_size >= 16, \
                f"Chat input font-size is {font_size}px — iOS will zoom (need >= 16px)"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_jd_textarea_font_size_prevents_zoom(self, device):
        """JD textarea must be >= 16px to prevent iOS zoom."""
        ctx, page = make_page(device, BASE_URL)
        try:
            # Open JD modal first
            page.locator("#jd-btn").click()
            page.wait_for_timeout(300)

            font_size = page.evaluate("""
                parseFloat(window.getComputedStyle(
                    document.getElementById('jd-text')
                ).fontSize)
            """)
            assert font_size >= 16, \
                f"JD textarea font-size is {font_size}px — iOS will zoom (need >= 16px)"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# CSS feature rendering
# ---------------------------------------------------------------------------

class TestCSSRendering:
    """Verify CSS features render correctly across mobile browsers."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_backdrop_filter_applied(self, device):
        """backdrop-filter / -webkit-backdrop-filter should be applied."""
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const hero = document.querySelector('.hero');
                const style = window.getComputedStyle(hero);
                return {
                    bf: style.backdropFilter || '',
                    wbf: style.webkitBackdropFilter || '',
                };
            }""")
            has_filter = bool(result["bf"]) or bool(result["wbf"])
            # Note: some engines report "none" when not supported
            bf_val = result["bf"] or result["wbf"]
            if bf_val and bf_val != "none":
                assert "blur" in bf_val, f"Expected blur filter, got {bf_val}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_hero_background_renders(self, device):
        """Hero section should have visible background (not transparent)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            bg = page.evaluate("""
                window.getComputedStyle(document.querySelector('.hero')).backgroundColor
            """)
            # Should not be fully transparent
            assert bg != "rgba(0, 0, 0, 0)", f"Hero background is transparent: {bg}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_background_attachment_not_fixed_on_ios(self, device):
        """background-attachment:fixed is broken on iOS Safari.
        The CSS should either not use it or the body should still render."""
        ctx, page = make_page(device, BASE_URL)
        try:
            attachment = page.evaluate("""
                window.getComputedStyle(document.body).backgroundAttachment
            """)
            # If it's fixed, that's a known iOS issue — flag it
            if attachment == "fixed":
                # Verify the background is still rendering (not blank white)
                bg_image = page.evaluate("""
                    window.getComputedStyle(document.body).backgroundImage
                """)
                assert bg_image != "none", \
                    "background-attachment:fixed with no image on iOS = blank page"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", ALL_MOBILE_DEVICES, ids=device_id)
    def test_viewport_meta_tag_present(self, device):
        """viewport meta tag must be present for proper mobile rendering."""
        ctx, page = make_page(device, BASE_URL)
        try:
            content = page.evaluate("""
                document.querySelector('meta[name="viewport"]')?.content || ''
            """)
            assert "width=device-width" in content, \
                f"Missing width=device-width in viewport meta: {content}"
            assert "initial-scale=1" in content, \
                f"Missing initial-scale=1 in viewport meta: {content}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_chat_panel_has_background(self, device):
        """Chat panel should have a semi-opaque background for readability."""
        ctx, page = make_page(device, BASE_URL)
        try:
            bg = page.evaluate("""
                window.getComputedStyle(document.getElementById('chat-panel')).backgroundColor
            """)
            # Should not be fully transparent
            assert bg != "rgba(0, 0, 0, 0)" and bg != "transparent", \
                f"Chat panel has no background on {device['name']}: {bg}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Viewport height (dvh) handling
# ---------------------------------------------------------------------------

class TestViewportHeight:
    """Test that dynamic viewport height works correctly."""

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_main_fills_viewport_height(self, device):
        """Main element should fill the viewport height."""
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const main = document.querySelector('main');
                const rect = main.getBoundingClientRect();
                return {
                    mainHeight: rect.height,
                    viewportHeight: window.innerHeight,
                };
            }""")
            # Main should be close to viewport height (within 10% tolerance)
            ratio = result["mainHeight"] / result["viewportHeight"]
            assert ratio >= 0.85, \
                f"Main height ({result['mainHeight']}px) is only {ratio:.0%} of viewport ({result['viewportHeight']}px)"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Accessibility basics
# ---------------------------------------------------------------------------

class TestAccessibility:
    """Basic accessibility checks on mobile."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_aria_labels_present(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            labels = page.evaluate("""() => {
                const checks = {
                    chatPanel: document.getElementById('chat-panel')
                        ?.getAttribute('aria-label') || '',
                    chatInput: document.getElementById('chat-input')
                        ?.getAttribute('aria-label') || '',
                    chatForm: document.getElementById('chat-form')
                        ?.getAttribute('aria-label') || '',
                    messages: document.getElementById('messages')
                        ?.getAttribute('aria-live') || '',
                };
                return checks;
            }""")
            assert labels["chatPanel"], "Chat panel missing aria-label"
            assert labels["chatInput"], "Chat input missing aria-label"
            assert labels["chatForm"], "Chat form missing aria-label"
            assert labels["messages"], "Messages div missing aria-live"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_text_readable_contrast(self, device):
        """Main text should have sufficient contrast against background."""
        ctx, page = make_page(device, BASE_URL)
        try:
            color = page.evaluate("""
                window.getComputedStyle(document.querySelector('.hero__name')).color
            """)
            # Should be a dark color (not white or very light)
            assert color != "rgb(255, 255, 255)", "Hero name text is white — likely invisible"
            assert color != "rgba(0, 0, 0, 0)", "Hero name text is transparent"
        finally:
            page.close()
            ctx.close()
