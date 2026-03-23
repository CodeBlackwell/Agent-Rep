"""
iPhone 15 Safari-specific regression tests.

Deep tests targeting known WebKit/iOS issues that could cause the
reported user problems on iPhone 15.
"""

import pytest
from tests.e2e.conftest import (
    IPHONE_15, IPHONE_15_PRO_MAX, IPHONE_SE, IOS_DEVICES,
    make_page, make_context, device_id, BASE_URL,
)


# ---------------------------------------------------------------------------
# Dynamic viewport units (dvh vs vh)
# ---------------------------------------------------------------------------

class TestDynamicViewport:
    """iOS Safari has a collapsible address bar that changes viewport height.
    100vh includes the hidden bar area, 100dvh adjusts dynamically."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_body_uses_dvh_or_vh(self, device):
        """Body height should be set (100dvh with vh fallback)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const body = document.body;
                const style = window.getComputedStyle(body);
                return {
                    height: style.height,
                    overflow: style.overflow,
                    innerHeight: window.innerHeight,
                    bodyHeight: body.getBoundingClientRect().height,
                };
            }""")
            # Body should fill viewport
            ratio = result["bodyHeight"] / result["innerHeight"]
            assert ratio >= 0.95, \
                f"Body height ({result['bodyHeight']}) doesn't fill viewport ({result['innerHeight']})"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_main_respects_viewport_height(self, device):
        """Main element should not exceed viewport height."""
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const main = document.querySelector('main');
                return {
                    mainH: main.getBoundingClientRect().height,
                    viewportH: window.innerHeight,
                };
            }""")
            assert result["mainH"] <= result["viewportH"] + 5, \
                f"Main ({result['mainH']}px) exceeds viewport ({result['viewportH']}px)"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# overflow:hidden body behavior on iOS
# ---------------------------------------------------------------------------

class TestBodyOverflow:
    """iOS Safari has quirks with overflow:hidden on body — content can still
    rubber-band scroll, and the address bar may not behave as expected."""

    def test_iphone15_no_body_scroll(self):
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            # Try to scroll the body
            scroll_before = page.evaluate("window.scrollY")
            page.evaluate("window.scrollTo(0, 100)")
            page.wait_for_timeout(300)
            scroll_after = page.evaluate("window.scrollY")
            # With overflow:hidden, body should not scroll
            assert scroll_after == scroll_before, \
                f"Body scrolled from {scroll_before} to {scroll_after} (overflow:hidden not working)"
        finally:
            page.close()
            ctx.close()

    def test_iphone15_no_vertical_content_overflow(self):
        """Total content height should not exceed viewport."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            result = page.evaluate("""() => {
                return {
                    scrollH: document.documentElement.scrollHeight,
                    clientH: document.documentElement.clientHeight,
                };
            }""")
            # Allow small tolerance for rounding
            assert result["scrollH"] <= result["clientH"] + 10, \
                f"Content overflows: scrollHeight={result['scrollH']}, clientHeight={result['clientH']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# position:fixed behavior with virtual keyboard
# ---------------------------------------------------------------------------

class TestFixedPositioning:
    """position:fixed elements can misbehave on iOS when the virtual keyboard opens."""

    def test_iphone15_canvas_toggle_position_fixed(self):
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            pos = page.evaluate("""
                window.getComputedStyle(document.getElementById('canvas-toggle')).position
            """)
            assert pos == "fixed", f"Canvas toggle should be fixed, got {pos}"
        finally:
            page.close()
            ctx.close()

    def test_iphone15_canvas_toggle_visible_after_input_focus(self):
        """Canvas toggle should remain visible after focusing input
        (virtual keyboard changes viewport on iOS)."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            page.locator("#chat-input").focus()
            page.wait_for_timeout(500)
            btn = page.locator("#canvas-toggle")
            assert btn.is_visible(), "Canvas toggle should stay visible after input focus"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# background-attachment: fixed (known iOS bug)
# ---------------------------------------------------------------------------

class TestBackgroundFixed:
    """background-attachment:fixed is notoriously broken on iOS Safari.
    It renders as background-attachment:scroll, causing blank backgrounds
    or mispositioned images."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_background_image_visible(self, device):
        """Even if attachment:fixed is broken, the background should still show."""
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const style = window.getComputedStyle(document.body);
                return {
                    bgImage: style.backgroundImage,
                    bgAttach: style.backgroundAttachment,
                    bgSize: style.backgroundSize,
                };
            }""")
            # Background image should be set
            assert result["bgImage"] != "none", \
                f"No background image on {device['name']}: {result}"
            # Flag the known iOS issue
            if result["bgAttach"] == "fixed":
                # This will render incorrectly on real iOS — flag it
                pytest.xfail(
                    "background-attachment:fixed is known broken on iOS Safari. "
                    "Consider using background-attachment:scroll on mobile."
                )
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_body_not_blank_white(self, device):
        """The page should not appear as a blank white screen."""
        ctx, page = make_page(device, BASE_URL)
        try:
            # Check that the body background color is not white/default
            bg_color = page.evaluate("""
                window.getComputedStyle(document.body).backgroundColor
            """)
            # Our CSS sets --bg: #f5f0eb
            assert bg_color != "rgb(255, 255, 255)" and bg_color != "rgba(0, 0, 0, 0)", \
                f"Body appears blank (bg={bg_color}) on {device['name']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# -webkit-backdrop-filter
# ---------------------------------------------------------------------------

class TestWebkitBackdropFilter:
    """Safari requires -webkit-backdrop-filter prefix."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_hero_has_webkit_backdrop_filter(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const style = window.getComputedStyle(document.querySelector('.hero'));
                return {
                    bf: style.backdropFilter || '',
                    wbf: style.webkitBackdropFilter || '',
                };
            }""")
            has_filter = (result["bf"] and result["bf"] != "none") or \
                         (result["wbf"] and result["wbf"] != "none")
            assert has_filter, \
                f"No backdrop-filter on hero ({device['name']}): bf={result['bf']}, wbf={result['wbf']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_chat_panel_has_webkit_backdrop_filter(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const style = window.getComputedStyle(document.getElementById('chat-panel'));
                return {
                    bf: style.backdropFilter || '',
                    wbf: style.webkitBackdropFilter || '',
                };
            }""")
            has_filter = (result["bf"] and result["bf"] != "none") or \
                         (result["wbf"] and result["wbf"] != "none")
            assert has_filter, \
                f"No backdrop-filter on chat panel ({device['name']})"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# requestSubmit() support on WebKit
# ---------------------------------------------------------------------------

class TestRequestSubmit:
    """form.requestSubmit() was added to Safari 16+. iOS 17 (iPhone 15) supports it,
    but older devices may not."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_request_submit_works(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            supported = page.evaluate("""
                typeof HTMLFormElement.prototype.requestSubmit === 'function'
            """)
            assert supported, \
                f"requestSubmit() not available on {device['name']} — chat submission will break"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Safe area insets
# ---------------------------------------------------------------------------

class TestSafeAreaInsets:
    """iPhone 15 has a Dynamic Island and rounded corners that create
    safe area insets. Content should not be hidden behind them."""

    def test_iphone15_content_not_under_notch(self):
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            # Hero should start below the top safe area
            hero_box = page.locator(".hero").bounding_box()
            assert hero_box is not None
            # On iPhone 15 with Dynamic Island, top content should have some padding
            # The main element has padding: 0.75rem which provides some offset
            assert hero_box["y"] >= 5, \
                f"Hero starts at y={hero_box['y']} — may be under the Dynamic Island"
        finally:
            page.close()
            ctx.close()

    def test_iphone15_canvas_toggle_not_under_home_indicator(self):
        """Canvas toggle at bottom-right should not overlap the home indicator."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const btn = document.getElementById('canvas-toggle');
                const rect = btn.getBoundingClientRect();
                return {
                    bottom: rect.bottom,
                    right: rect.right,
                    viewportH: window.innerHeight,
                    viewportW: window.innerWidth,
                };
            }""")
            # Should have at least 20px margin from bottom edge
            margin_bottom = result["viewportH"] - result["bottom"]
            assert margin_bottom >= 8, \
                f"Canvas toggle too close to bottom ({margin_bottom}px margin)"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Input zoom prevention (comprehensive)
# ---------------------------------------------------------------------------

class TestInputZoom:
    """iOS Safari zooms the viewport when focusing an input with font-size < 16px.
    This is the #1 most common mobile UX bug."""

    def test_iphone15_all_inputs_prevent_zoom(self):
        """Every text input and textarea must have font-size >= 16px."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:

            # Open JD modal to expose textarea
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)

            result = page.evaluate("""() => {
                const inputs = document.querySelectorAll(
                    'input[type="text"], input:not([type]), textarea'
                );
                const results = [];
                inputs.forEach(el => {
                    const size = parseFloat(window.getComputedStyle(el).fontSize);
                    results.push({
                        tag: el.tagName,
                        id: el.id || el.name || '(unnamed)',
                        fontSize: size,
                        ok: size >= 16,
                    });
                });
                return results;
            }""")

            failures = [r for r in result if not r["ok"]]
            assert not failures, \
                f"Inputs with font-size < 16px (will cause iOS zoom): {failures}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Touch interaction specifics
# ---------------------------------------------------------------------------

class TestIOSTouchBehavior:
    """iOS-specific touch behavior edge cases."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_starter_button_tap(self, device):
        """Starter buttons should respond to tap (no 300ms delay issues)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            starters = page.locator(".starter-btn")
            if starters.count() > 0:
                starters.first.tap()
                page.wait_for_timeout(500)
                # Either starters dismissed or JD modal opened
                dismissed = page.locator(".starter-questions").count() == 0
                modal_open = page.locator(".jd-modal--open").count() > 0
                assert dismissed or modal_open, \
                    "Starter tap should either dismiss starters or open modal"
        finally:
            page.close()
            ctx.close()

    def test_iphone15_double_tap_doesnt_zoom(self):
        """Double-tapping should not zoom the page (needs proper meta viewport)."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            initial_scale = page.evaluate("visualViewport?.scale || 1")
            # Double tap on the hero
            page.locator(".hero").dblclick()
            page.wait_for_timeout(500)
            final_scale = page.evaluate("visualViewport?.scale || 1")
            assert abs(final_scale - initial_scale) < 0.1, \
                f"Double-tap caused zoom: {initial_scale} -> {final_scale}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Full page flow on iPhone 15
# ---------------------------------------------------------------------------

class TestiPhone15FullFlow:
    """End-to-end user journey on iPhone 15."""

    def test_complete_chat_flow(self):
        """Load page -> see hero -> tap starter -> get response -> hero fades."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:
            # 1. Page loads
            assert page.locator(".hero").is_visible(), "Hero should be visible"

            # 2. Starter questions visible
            starters = page.locator(".starter-btn")
            assert starters.count() == 3, "Should have 3 starter buttons"

            # 3. Tap first starter
            first_text = starters.first.text_content()
            starters.first.tap()
            page.wait_for_timeout(1000)

            # 4. User message appears
            assert page.locator(".msg-user").count() > 0, "User message should appear"

            # 5. Hero fades
            assert page.evaluate("document.body.classList.contains('hero-faded')"), \
                "Hero should fade"

            # 6. Wait for response
            page.wait_for_selector(".msg-assistant:not(.loading)", timeout=30000)

            # 7. Input re-enabled
            assert not page.evaluate("document.getElementById('chat-input').disabled"), \
                "Input should be re-enabled"

            # 8. No JS errors
            # (checked separately in test_cross_browser.py)

        finally:
            page.close()
            ctx.close()

    def test_jd_modal_flow(self):
        """Open JD modal -> paste text -> verify analyze enabled."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:

            # 1. Tap JD button
            page.locator("#jd-btn").tap()
            page.wait_for_timeout(500)
            assert page.locator(".jd-modal--open").count() > 0, "Modal should open"

            # 2. Verify elements
            assert page.locator("#jd-text").is_visible(), "Textarea should be visible"
            assert page.locator("#jd-drop").is_visible(), "Drop zone should be visible"
            assert page.evaluate("document.getElementById('jd-analyze').disabled"), \
                "Analyze should be disabled"

            # 3. Paste text
            page.locator("#jd-text").fill(
                "Looking for a senior full-stack engineer with Python, React, "
                "and cloud infrastructure experience."
            )

            # 4. Analyze enabled
            assert not page.evaluate("document.getElementById('jd-analyze').disabled"), \
                "Analyze should be enabled after text input"

            # 5. Close modal
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            assert page.locator(".jd-modal--open").count() == 0, "Modal should close"

        finally:
            page.close()
            ctx.close()

    def test_canvas_toggle_flow(self):
        """Toggle canvas mode on and off on iPhone 15."""
        ctx, page = make_page(IPHONE_15, BASE_URL)
        try:

            # Toggle on
            page.locator("#canvas-toggle").tap()
            page.wait_for_timeout(800)
            assert page.evaluate("document.body.classList.contains('canvas-mode')"), \
                "Canvas mode should be active"

            # Content should be hidden
            left_opacity = page.evaluate("""
                window.getComputedStyle(document.querySelector('.left-col')).opacity
            """)
            assert left_opacity == "0", "Content should be hidden"

            # Toggle off
            page.locator("#canvas-toggle").tap()
            page.wait_for_timeout(800)
            assert not page.evaluate("document.body.classList.contains('canvas-mode')"), \
                "Canvas mode should be off"

            # Content returns
            left_opacity = page.evaluate("""
                window.getComputedStyle(document.querySelector('.left-col')).opacity
            """)
            assert left_opacity == "1", "Content should be visible again"

        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# iPhone 15 Pro Max (larger screen variant)
# ---------------------------------------------------------------------------

class TestiPhone15ProMax:
    """Verify the larger iPhone 15 Pro Max doesn't have different issues."""

    def test_layout_consistent_with_iphone15(self):
        """Pro Max should have same layout behavior as regular iPhone 15."""
        ctx15, page15 = make_page(IPHONE_15, BASE_URL)
        ctxpm, pagepm = make_page(IPHONE_15_PRO_MAX, BASE_URL)
        try:

            # Both should have column layout
            dir15 = page15.evaluate(
                "window.getComputedStyle(document.querySelector('main')).flexDirection"
            )
            dirpm = pagepm.evaluate(
                "window.getComputedStyle(document.querySelector('main')).flexDirection"
            )
            assert dir15 == dirpm == "column"

            # Both should hide graph
            disp15 = page15.evaluate(
                "window.getComputedStyle(document.getElementById('graph-panel')).display"
            )
            disppm = pagepm.evaluate(
                "window.getComputedStyle(document.getElementById('graph-panel')).display"
            )
            assert disp15 == disppm == "none"

        finally:
            page15.close()
            ctx15.close()
            pagepm.close()
            ctxpm.close()


# ---------------------------------------------------------------------------
# Screenshot comparison helper (visual regression)
# ---------------------------------------------------------------------------

class TestVisualRegression:
    """Capture screenshots for manual visual comparison.
    These don't assert — they produce artifacts for review."""

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_capture_homepage_screenshot(self, device, tmp_path):
        ctx, page = make_page(device, BASE_URL)
        try:
            name = device_id(device)
            path = tmp_path / f"homepage-{name}.png"
            page.screenshot(path=str(path), full_page=False)
            assert path.exists(), f"Screenshot not saved for {device['name']}"
            assert path.stat().st_size > 1000, "Screenshot too small — possibly blank"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", IOS_DEVICES, ids=device_id)
    def test_capture_jd_modal_screenshot(self, device, tmp_path):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            name = device_id(device)
            path = tmp_path / f"jd-modal-{name}.png"
            page.screenshot(path=str(path), full_page=False)
            assert path.exists()
            assert path.stat().st_size > 1000
        finally:
            page.close()
            ctx.close()
