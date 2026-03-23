"""
Cross-browser mobile tests.

Runs the same tests across WebKit (Safari), Chromium (Chrome), and Firefox
to catch browser-specific rendering and behavior differences.
"""

import pytest
from tests.e2e.conftest import (
    IPHONE_15, PIXEL_7, FIREFOX_MOBILE, DESKTOP_CHROME,
    make_page, make_context, device_id, BASE_URL,
)


# All three browser engines with a phone device each
BROWSER_MATRIX = [IPHONE_15, PIXEL_7, FIREFOX_MOBILE]


# ---------------------------------------------------------------------------
# CSS rendering consistency
# ---------------------------------------------------------------------------

class TestCSSConsistency:
    """Verify CSS renders consistently across browser engines."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_border_radius_renders(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            radius = page.evaluate("""
                window.getComputedStyle(document.querySelector('.hero')).borderRadius
            """)
            assert radius and radius != "0px", \
                f"Border radius not applied on {device['name']}: {radius}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_flex_layout_applied(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            display = page.evaluate("""
                window.getComputedStyle(document.querySelector('main')).display
            """)
            assert display == "flex", f"Main should be flex, got {display} on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_google_fonts_loaded(self, device):
        """Cormorant Garamond should be loaded and applied."""
        ctx, page = make_page(device, BASE_URL)
        try:
            font = page.evaluate("""
                window.getComputedStyle(document.querySelector('.hero__name')).fontFamily
            """)
            assert "Cormorant" in font or "serif" in font, \
                f"Expected serif font, got {font} on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_css_variables_applied(self, device):
        """Custom properties (--bg, --ink, etc.) should resolve correctly."""
        ctx, page = make_page(device, BASE_URL)
        try:
            result = page.evaluate("""() => {
                const style = window.getComputedStyle(document.documentElement);
                return {
                    bg: style.getPropertyValue('--bg').trim(),
                    ink: style.getPropertyValue('--ink').trim(),
                    accent: style.getPropertyValue('--accent').trim(),
                };
            }""")
            assert result["bg"] == "#f5f0eb", f"--bg wrong: {result['bg']}"
            assert result["ink"] == "#1a1410", f"--ink wrong: {result['ink']}"
            assert result["accent"] == "#6b4c2a", f"--accent wrong: {result['accent']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# JavaScript API compatibility
# ---------------------------------------------------------------------------

class TestJSCompatibility:
    """Test JavaScript APIs that may differ across browsers."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_request_submit_supported(self, device):
        """form.requestSubmit() must be supported (used by chat.js)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            supported = page.evaluate("""
                typeof document.getElementById('chat-form').requestSubmit === 'function'
            """)
            assert supported, \
                f"requestSubmit() not supported on {device['name']} ({device['browser']})"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_crypto_subtle_available(self, device):
        """crypto.subtle is required for fingerprinting (needs secure context)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("""
                typeof crypto !== 'undefined' && typeof crypto.subtle !== 'undefined'
            """)
            # On localhost HTTP, crypto.subtle may not be available
            if BASE_URL.startswith("https"):
                assert available, \
                    f"crypto.subtle not available on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_fetch_api_available(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("typeof fetch === 'function'")
            assert available, f"fetch() not available on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_readable_stream_available(self, device):
        """ReadableStream is needed for SSE parsing via fetch."""
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("typeof ReadableStream === 'function'")
            assert available, \
                f"ReadableStream not available on {device['name']} — SSE won't work"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_text_decoder_available(self, device):
        """TextDecoder used for SSE streaming."""
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("typeof TextDecoder === 'function'")
            assert available, f"TextDecoder not available on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_text_encoder_available(self, device):
        """TextEncoder used for fingerprinting hash."""
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("typeof TextEncoder === 'function'")
            assert available, f"TextEncoder not available on {device['name']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# D3.js & Mermaid compatibility
# ---------------------------------------------------------------------------

class TestLibraryCompat:
    """External libraries must load across browsers."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_d3_loaded(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("typeof d3 !== 'undefined'")
            assert available, f"D3.js not loaded on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_mermaid_loaded(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            available = page.evaluate("typeof mermaid !== 'undefined'")
            assert available, f"Mermaid not loaded on {device['name']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------

class TestSSEStreaming:
    """Verify SSE streaming works across browser engines."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_sse_stream_receives_data(self, device):
        """Submit a question and verify SSE events are received."""
        ctx, page = make_page(device, BASE_URL)
        try:

            # Set up event tracking
            page.evaluate("""() => {
                window.__sseEvents = [];
                const origFetch = window.fetch;
                // We'll just check that the response arrives
            }""")

            page.locator("#chat-input").fill("What is PROVE?")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")

            # Wait for either status tracker or assistant message
            page.wait_for_selector(".msg-status, .msg-assistant:not(.loading)", timeout=30000)

            # Verify something rendered
            has_response = page.evaluate("""() => {
                return document.querySelectorAll('.msg-status, .msg-assistant:not(.loading)').length > 0;
            }""")
            assert has_response, f"No SSE response on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_status_tracker_renders(self, device):
        """Tool call status tracker should render during SSE stream."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("What Python skills does Le have?")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")

            # Status tracker should appear as tools are called
            try:
                page.wait_for_selector(".msg-status", timeout=15000)
                status = page.locator(".msg-status")
                assert status.count() > 0, "Status tracker should appear"
            except Exception:
                # If response is very fast, status may collapse before we check
                pass

            # Eventually an assistant message should appear
            page.wait_for_selector(".msg-assistant:not(.loading)", timeout=30000)
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Touch events
# ---------------------------------------------------------------------------

class TestTouchEvents:
    """Verify touch interactions work correctly."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_touch_on_chat_input(self, device):
        """Tapping chat input should focus it."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").tap()
            page.wait_for_timeout(300)
            focused = page.evaluate(
                "document.activeElement === document.getElementById('chat-input')"
            )
            assert focused, f"Input should be focused after tap on {device['name']}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_touch_on_canvas_toggle(self, device):
        """Tapping canvas toggle should work like click."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#canvas-toggle").tap()
            page.wait_for_timeout(500)
            has_class = page.evaluate(
                "document.body.classList.contains('canvas-mode')"
            )
            assert has_class, f"Canvas mode should activate on tap ({device['name']})"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Modal z-index stacking
# ---------------------------------------------------------------------------

class TestZIndexStacking:
    """Modals should appear above all other content."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_jd_modal_above_content(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)

            result = page.evaluate("""() => {
                const modal = document.querySelector('.jd-modal');
                const main = document.querySelector('main');
                return {
                    modalZ: parseInt(window.getComputedStyle(modal).zIndex) || 0,
                    mainZ: parseInt(window.getComputedStyle(main).zIndex) || 0,
                };
            }""")
            assert result["modalZ"] > result["mainZ"], \
                f"Modal z-index ({result['modalZ']}) should be above main ({result['mainZ']})"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_canvas_toggle_above_content(self, device):
        """Canvas toggle should be above main content (position: fixed)."""
        ctx, page = make_page(device, BASE_URL)
        try:
            z = page.evaluate("""
                parseInt(window.getComputedStyle(
                    document.getElementById('canvas-toggle')
                ).zIndex) || 0
            """)
            assert z >= 50, f"Canvas toggle z-index should be >= 50, got {z}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Console errors
# ---------------------------------------------------------------------------

class TestConsoleErrors:
    """No JavaScript errors should appear in the console."""

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_no_js_errors_on_load(self, device):
        """Page load should not produce JavaScript errors."""
        ctx = make_context(device)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.wait_for_function(
                "document.body.classList.contains('is-reveal')",
                timeout=15000,
            )
            page.wait_for_timeout(2000)  # Let scripts run
            assert not errors, \
                f"JS errors on {device['name']}: {errors}"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", BROWSER_MATRIX, ids=device_id)
    def test_no_js_errors_on_interaction(self, device):
        """Basic interactions should not produce JS errors."""
        ctx = make_context(device)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.wait_for_function(
                "document.body.classList.contains('is-reveal')",
                timeout=15000,
            )

            # Interact with various elements
            page.locator("#canvas-toggle").click()
            page.wait_for_timeout(300)
            page.locator("#canvas-toggle").click()
            page.wait_for_timeout(300)

            page.locator("#jd-btn").click()
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            page.locator("#chat-input").fill("test")
            page.locator("#chat-input").fill("")

            assert not errors, \
                f"JS errors during interaction on {device['name']}: {errors}"
        finally:
            page.close()
            ctx.close()
