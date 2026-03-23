"""
Mobile interaction tests.

Covers chat form, starter questions, hero fade, JD modal,
canvas toggle, scroll behavior, rate limiting UI, and skill pages.
"""

import pytest
from tests.e2e.conftest import (
    ALL_MOBILE_DEVICES, PHONE_DEVICES, IOS_DEVICES, CROSS_BROWSER_DEVICES,
    IPHONE_15, IPHONE_15_PRO_MAX, IPHONE_SE, PIXEL_7, GALAXY_S23,
    GALAXY_FOLD, FIREFOX_MOBILE, DESKTOP_CHROME,
    make_page, device_id, BASE_URL,
)


# ---------------------------------------------------------------------------
# Chat form
# ---------------------------------------------------------------------------

class TestChatForm:
    """Chat input, submission, and message rendering on mobile."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_chat_input_visible_and_focusable(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            inp = page.locator("#chat-input")
            assert inp.is_visible(), "Chat input should be visible"
            inp.focus()
            is_focused = page.evaluate(
                "document.activeElement === document.getElementById('chat-input')"
            )
            assert is_focused, "Chat input should be focusable"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_chat_input_accepts_text(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            inp = page.locator("#chat-input")
            inp.fill("test question")
            value = inp.input_value()
            assert value == "test question", f"Input value is '{value}'"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_empty_submit_does_nothing(self, device):
        """Submitting empty input should not add any messages."""
        ctx, page = make_page(device, BASE_URL)
        try:
            initial_count = page.locator(".msg").count()
            page.locator("#chat-input").fill("")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            page.wait_for_timeout(500)
            final_count = page.locator(".msg").count()
            assert final_count == initial_count, "Empty submit should not create messages"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_chat_form_submit_creates_user_message(self, device):
        """Typing and submitting should create a user message bubble."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("What are Le's skills?")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            # User message should appear
            page.wait_for_selector(".msg-user", timeout=3000)
            msg = page.locator(".msg-user").last
            assert "What are Le's skills?" in msg.text_content()
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_loading_dots_appear_after_submit(self, device):
        """Loading animation should appear while waiting for response."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("Tell me about Python skills")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            # Either loading dots or status tracker should appear
            page.wait_for_selector(".loading, .msg-status", timeout=5000)
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_input_disabled_during_request(self, device):
        """Chat input should be disabled while a request is in flight."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("Hello")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            page.wait_for_timeout(200)
            disabled = page.evaluate(
                "document.getElementById('chat-input').disabled"
            )
            assert disabled, "Input should be disabled during request"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_sse_response_renders(self, device):
        """After submitting, an assistant response should eventually appear."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("What is PROVE?")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            # Wait for assistant response (SSE streaming)
            page.wait_for_selector(".msg-assistant:not(.loading)", timeout=30000)
            response = page.locator(".msg-assistant:not(.loading)").last
            text = response.text_content()
            assert len(text) > 10, f"Response too short: '{text}'"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Starter questions
# ---------------------------------------------------------------------------

class TestStarterQuestions:
    """Starter question buttons and their behavior."""

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_starter_questions_visible(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            starters = page.locator(".starter-btn")
            count = starters.count()
            assert count == 3, f"Expected 3 starter buttons, got {count}"
            for i in range(count):
                assert starters.nth(i).is_visible(), f"Starter button {i} not visible"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_tapping_starter_submits_question(self, device):
        """Tapping a query-type starter should submit a question."""
        ctx, page = make_page(device, BASE_URL)
        try:
            # Find the first query-type starter (not the JD one)
            starters = page.locator(".starter-btn")
            # The first two are query starters, the third is JD
            starters.first.click()
            page.wait_for_timeout(1000)
            # Starter buttons should be dismissed
            remaining = page.locator(".starter-questions").count()
            assert remaining == 0, "Starter questions should disappear after clicking"
            # User message should appear
            user_msgs = page.locator(".msg-user")
            assert user_msgs.count() > 0, "User message should appear after starter click"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_starter_opens_modal(self, device):
        """The 'Analyze a job description' starter should open the JD modal."""
        ctx, page = make_page(device, BASE_URL)
        try:
            starters = page.locator(".starter-btn")
            # Click the last one (JD starter)
            starters.last.click()
            page.wait_for_timeout(500)
            modal = page.locator(".jd-modal--open")
            assert modal.count() > 0, "JD modal should open"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Hero fade animation
# ---------------------------------------------------------------------------

class TestHeroFade:
    """Hero should fade away on first question, giving chat more room."""

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_hero_visible_initially(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            hero = page.locator(".hero")
            box = hero.bounding_box()
            assert box is not None, "Hero should be visible"
            assert box["height"] > 50, f"Hero too small: {box['height']}px"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_hero_fades_on_first_question(self, device):
        """After first question, body should get hero-faded class."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("Hello")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            page.wait_for_timeout(500)
            has_class = page.evaluate(
                "document.body.classList.contains('hero-faded')"
            )
            assert has_class, "Body should have hero-faded class after first question"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_hero_collapses_height_on_mobile(self, device):
        """On mobile, hero should collapse to 0 height after fade."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#chat-input").fill("Hello")
            page.evaluate("document.getElementById('chat-form').requestSubmit()")
            # Wait for the CSS transition (1.2s)
            page.wait_for_timeout(2000)
            hero_h = page.evaluate("""
                document.querySelector('.hero').getBoundingClientRect().height
            """)
            assert hero_h < 5, f"Hero should collapse on mobile, height is {hero_h}px"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# JD Modal
# ---------------------------------------------------------------------------

class TestJDModal:
    """Job description analysis modal on mobile."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_modal_opens_from_button(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            modal = page.locator(".jd-modal--open")
            assert modal.count() > 0, "JD modal should be open"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_modal_closes_on_backdrop_click(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            page.locator(".jd-modal__backdrop").click(force=True)
            page.wait_for_timeout(500)
            modal = page.locator(".jd-modal--open")
            assert modal.count() == 0, "Modal should close on backdrop click"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_modal_closes_on_x_button(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            page.locator(".jd-modal__close").click()
            page.wait_for_timeout(500)
            modal = page.locator(".jd-modal--open")
            assert modal.count() == 0, "Modal should close on X click"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_modal_closes_on_escape(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            modal = page.locator(".jd-modal--open")
            assert modal.count() == 0, "Modal should close on Escape"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_jd_modal_fits_viewport(self, device):
        """Modal panel should not overflow the viewport on mobile."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            result = page.evaluate("""() => {
                const panel = document.querySelector('.jd-modal__panel');
                const rect = panel.getBoundingClientRect();
                return {
                    right: rect.right,
                    bottom: rect.bottom,
                    viewportW: window.innerWidth,
                    viewportH: window.innerHeight,
                };
            }""")
            assert result["right"] <= result["viewportW"] + 5, \
                f"Modal overflows right: {result['right']} > {result['viewportW']}"
            # Bottom may scroll, but check it's not wildly off
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_analyze_button_disabled_initially(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            disabled = page.evaluate(
                "document.getElementById('jd-analyze').disabled"
            )
            assert disabled, "Analyze button should be disabled without input"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_jd_analyze_enabled_after_text_input(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            page.locator("#jd-text").fill("Senior Python developer needed...")
            disabled = page.evaluate(
                "document.getElementById('jd-analyze').disabled"
            )
            assert not disabled, "Analyze button should be enabled after text input"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_jd_drop_zone_visible(self, device):
        """File drop zone should be visible and tappable."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#jd-btn").click()
            page.wait_for_timeout(500)
            drop = page.locator("#jd-drop")
            assert drop.is_visible(), "Drop zone should be visible"
            box = drop.bounding_box()
            assert box["width"] > 100, f"Drop zone too narrow: {box['width']}px"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Canvas toggle
# ---------------------------------------------------------------------------

class TestCanvasToggle:
    """Background canvas view toggle."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_canvas_toggle_visible(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            btn = page.locator("#canvas-toggle")
            assert btn.is_visible(), "Canvas toggle should be visible"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_canvas_toggle_adds_class(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#canvas-toggle").click()
            page.wait_for_timeout(300)
            has_class = page.evaluate(
                "document.body.classList.contains('canvas-mode')"
            )
            assert has_class, "Body should have canvas-mode class"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_canvas_toggle_toggles_off(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#canvas-toggle").click()
            page.wait_for_timeout(300)
            page.locator("#canvas-toggle").click()
            page.wait_for_timeout(300)
            has_class = page.evaluate(
                "document.body.classList.contains('canvas-mode')"
            )
            assert not has_class, "canvas-mode should toggle off"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_canvas_mode_hides_content_on_mobile(self, device):
        """In canvas mode, left-col should slide away."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.locator("#canvas-toggle").click()
            page.wait_for_timeout(800)
            opacity = page.evaluate("""
                window.getComputedStyle(document.querySelector('.left-col')).opacity
            """)
            assert opacity == "0", f"Left col should be invisible in canvas mode, opacity={opacity}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Messages scroll
# ---------------------------------------------------------------------------

class TestMessageScroll:
    """Message container scrolling behavior."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_messages_container_scrollable(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            overflow = page.evaluate("""
                window.getComputedStyle(document.getElementById('messages')).overflowY
            """)
            assert overflow in ("auto", "scroll"), \
                f"Messages should be scrollable, got overflow-y: {overflow}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Skill detail page
# ---------------------------------------------------------------------------

class TestSkillPage:
    """Skill detail page rendering on mobile."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_skill_404_renders(self, device):
        """Non-existent skill should show 404 message, not crash."""
        ctx, page = make_page(device, f"{BASE_URL}/skills/nonexistent-skill-xyz",
                              wait_for_load=False)
        try:
            page.wait_for_load_state("domcontentloaded")
            content = page.text_content("body")
            assert "not found" in content.lower() or "Not Found" in content, \
                "Should show not-found message"
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", PHONE_DEVICES, ids=device_id)
    def test_skill_page_readable_on_mobile(self, device):
        """Skill page should have readable layout on mobile."""
        ctx, page = make_page(device, f"{BASE_URL}/skills/python",
                              wait_for_load=False)
        try:
            page.wait_for_load_state("domcontentloaded")
            # Check it loaded something (either skill data or 404)
            title = page.title()
            assert title, "Page should have a title"
            # Content should not overflow
            overflow = page.evaluate("""
                document.documentElement.scrollWidth > document.documentElement.clientWidth
            """)
            assert not overflow, f"Skill page overflows horizontally on {device['name']}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# Fingerprint generation
# ---------------------------------------------------------------------------

class TestFingerprint:
    """Browser fingerprint generation for rate limiting."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_fingerprint_generated(self, device):
        """window.__fp should be set after page load."""
        ctx, page = make_page(device, BASE_URL)
        try:
            page.wait_for_timeout(2000)
            fp = page.evaluate("window.__fp")
            assert fp, "Fingerprint should be generated"
            assert fp != "unknown", "Fingerprint should not be 'unknown'"
            assert len(fp) == 16, f"Fingerprint should be 16 chars, got {len(fp)}"
        finally:
            page.close()
            ctx.close()


# ---------------------------------------------------------------------------
# SEO meta tags
# ---------------------------------------------------------------------------

class TestSEO:
    """SEO meta tags should be present on mobile."""

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_og_tags_present(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            og_title = page.evaluate(
                "document.querySelector('meta[property=\"og:title\"]')?.content || ''"
            )
            og_image = page.evaluate(
                "document.querySelector('meta[property=\"og:image\"]')?.content || ''"
            )
            assert og_title, "og:title should be present"
            assert og_image, "og:image should be present"
            assert "PROVE" in og_title
        finally:
            page.close()
            ctx.close()

    @pytest.mark.parametrize("device", CROSS_BROWSER_DEVICES, ids=device_id)
    def test_structured_data_present(self, device):
        ctx, page = make_page(device, BASE_URL)
        try:
            ld_json = page.evaluate("""
                document.querySelector('script[type="application/ld+json"]')?.textContent || ''
            """)
            assert ld_json, "JSON-LD structured data should be present"
            assert "ProfilePage" in ld_json or "Person" in ld_json
        finally:
            page.close()
            ctx.close()
