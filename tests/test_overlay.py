"""Tests for RecordingOverlay and PreviewOverlay."""

from __future__ import annotations

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="overlay is macOS-only")


# ---------------------------------------------------------------------------
# Helpers — patch AppKit at the module level so imports succeed without a display
# ---------------------------------------------------------------------------


def _make_overlay_module():
    """Import overlay module with AppKit already available (macOS-only tests)."""
    from whisper_dic.overlay import PreviewOverlay, RecordingOverlay

    return RecordingOverlay, PreviewOverlay


# ---------------------------------------------------------------------------
# RecordingOverlay
# ---------------------------------------------------------------------------


class TestRecordingOverlayInit:
    def test_initial_state(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()

        assert overlay._window is None
        assert overlay._dot is None
        assert overlay._pulsing is False
        assert overlay._reduced_motion is False
        assert overlay._high_contrast is False
        assert overlay._pulse_thread is None
        assert isinstance(overlay._lock, type(threading.Lock()))

    def test_class_constants(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()

        assert RecordingOverlay.DOT_SIZE == 12
        assert RecordingOverlay._PULSE_INTERVAL == 0.08
        assert RecordingOverlay._PULSE_SPEED == 2.5


class TestRecordingOverlayAccessibility:
    def test_configure_accessibility_stores_preferences(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()

        with patch("whisper_dic.overlay.callAfter"):
            overlay.configure_accessibility(reduced_motion=True, high_contrast=True)

        assert overlay._reduced_motion is True
        assert overlay._high_contrast is True

    def test_configure_accessibility_stops_pulse_when_reduced_motion(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._pulsing = True
        overlay._pulse_thread = MagicMock()

        with patch("whisper_dic.overlay.callAfter"):
            overlay.configure_accessibility(reduced_motion=True, high_contrast=False)

        assert overlay._pulsing is False
        assert overlay._pulse_stop.is_set()

    def test_configure_accessibility_dispatches_style_to_main_thread(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.configure_accessibility(reduced_motion=False, high_contrast=True)

        mock_call_after.assert_called_once_with(overlay._apply_accessibility_style)

    def test_apply_accessibility_style_noop_without_window(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._window = None
        # Should not raise
        overlay._apply_accessibility_style()

    def test_apply_accessibility_style_high_contrast(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._high_contrast = True
        overlay._window = MagicMock()

        overlay._apply_accessibility_style()

        overlay._window.setAlphaValue_.assert_called_once_with(1.0)

    def test_apply_accessibility_style_normal(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._high_contrast = False
        overlay._window = MagicMock()

        overlay._apply_accessibility_style()

        overlay._window.setAlphaValue_.assert_called_once_with(0.85)


class TestRecordingOverlayShowHide:
    def test_show_recording_dispatches_to_main_thread(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.show_recording()

        mock_call_after.assert_called_once()
        args = mock_call_after.call_args.args
        assert args[0] == overlay._show
        # Second arg is NSColor.redColor()
        assert args[2] is True  # pulse=True

    def test_show_transcribing_dispatches_to_main_thread(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.show_transcribing()

        mock_call_after.assert_called_once()
        args = mock_call_after.call_args.args
        assert args[0] == overlay._show
        assert args[2] is False  # pulse=False

    def test_hide_stops_pulse_and_dispatches(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._pulsing = True
        overlay._pulse_thread = MagicMock()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.hide()

        assert overlay._pulsing is False
        assert overlay._pulse_stop.is_set()
        mock_call_after.assert_called_once_with(overlay._hide)

    def test_show_calls_ensure_window(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()

        with patch.object(overlay, "_ensure_window") as mock_ensure:
            overlay._dot = MagicMock()
            overlay._window = MagicMock()
            overlay._show(NSColor.redColor(), True)

        mock_ensure.assert_called_once()

    def test_show_returns_early_if_no_dot(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = None

        with patch.object(overlay, "_ensure_window"):
            # Should not raise
            overlay._show(NSColor.redColor(), True)

    def test_show_sets_color_and_orders_front(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = MagicMock()
        overlay._window = MagicMock()

        color = NSColor.orangeColor()
        with patch.object(overlay, "_ensure_window"):
            overlay._show(color, False)

        assert overlay._dot._color == color
        overlay._dot.setNeedsDisplay_.assert_called_once_with(True)
        overlay._window.orderFront_.assert_called_once_with(None)

    def test_show_with_pulse_starts_pulse(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = MagicMock()
        overlay._window = MagicMock()
        overlay._reduced_motion = False

        with patch.object(overlay, "_ensure_window"), patch.object(overlay, "_start_pulse") as mock_start:
            overlay._show(NSColor.redColor(), True)

        mock_start.assert_called_once()

    def test_show_without_pulse_stops_pulse(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = MagicMock()
        overlay._window = MagicMock()

        with patch.object(overlay, "_ensure_window"), patch.object(overlay, "_stop_pulse") as mock_stop:
            overlay._show(NSColor.orangeColor(), False)

        mock_stop.assert_called_once()

    def test_show_with_reduced_motion_stops_pulse_instead(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = MagicMock()
        overlay._window = MagicMock()
        overlay._reduced_motion = True

        with (
            patch.object(overlay, "_ensure_window"),
            patch.object(overlay, "_start_pulse") as mock_start,
            patch.object(overlay, "_stop_pulse") as mock_stop,
        ):
            overlay._show(NSColor.redColor(), True)

        mock_start.assert_not_called()
        mock_stop.assert_called_once()

    def test_show_alpha_high_contrast(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = MagicMock()
        overlay._window = MagicMock()
        overlay._high_contrast = True

        with patch.object(overlay, "_ensure_window"):
            overlay._show(NSColor.redColor(), False)

        overlay._window.setAlphaValue_.assert_called_with(1.0)

    def test_show_alpha_normal(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        from AppKit import NSColor

        overlay = RecordingOverlay()
        overlay._dot = MagicMock()
        overlay._window = MagicMock()
        overlay._high_contrast = False

        with patch.object(overlay, "_ensure_window"):
            overlay._show(NSColor.redColor(), False)

        overlay._window.setAlphaValue_.assert_called_with(0.85)

    def test_hide_orders_out(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._window = MagicMock()

        overlay._hide()

        overlay._window.orderOut_.assert_called_once_with(None)

    def test_hide_noop_without_window(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._window = None
        # Should not raise
        overlay._hide()


class TestRecordingOverlayPulse:
    def test_start_pulse_creates_thread(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._reduced_motion = False

        with patch("whisper_dic.overlay.callAfter"):
            overlay._start_pulse()

            assert overlay._pulsing is True
            assert overlay._pulse_thread is not None
            assert overlay._pulse_thread.daemon is True
            assert overlay._pulse_thread.name == "dot-pulse"

            # Stop and wait for the thread to fully exit while patch is active
            thread = overlay._pulse_thread
            overlay._stop_pulse()
            thread.join(timeout=1.0)

    def test_start_pulse_noop_when_already_pulsing(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._pulsing = True
        original_thread = overlay._pulse_thread

        overlay._start_pulse()

        assert overlay._pulse_thread is original_thread

    def test_start_pulse_noop_when_reduced_motion(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._reduced_motion = True

        overlay._start_pulse()

        assert overlay._pulsing is False
        assert overlay._pulse_thread is None

    def test_stop_pulse_sets_flags_and_joins(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        mock_thread = MagicMock()
        overlay._pulsing = True
        overlay._pulse_thread = mock_thread

        overlay._stop_pulse()

        assert overlay._pulsing is False
        assert overlay._pulse_stop.is_set()
        mock_thread.join.assert_called_once_with(timeout=0.5)
        assert overlay._pulse_thread is None

    def test_stop_pulse_noop_without_thread(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._pulsing = False
        overlay._pulse_thread = None

        # Should not raise
        overlay._stop_pulse()
        assert overlay._pulse_stop.is_set()

    def test_set_alpha_updates_window_when_pulsing(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._window = MagicMock()
        overlay._pulsing = True

        overlay._set_alpha(0.7)

        overlay._window.setAlphaValue_.assert_called_once_with(0.7)

    def test_set_alpha_noop_when_not_pulsing(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._window = MagicMock()
        overlay._pulsing = False

        overlay._set_alpha(0.7)

        overlay._window.setAlphaValue_.assert_not_called()

    def test_set_alpha_noop_without_window(self) -> None:
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()
        overlay._window = None
        overlay._pulsing = True

        # Should not raise
        overlay._set_alpha(0.7)

    def test_pulse_loop_dispatches_alpha_updates(self) -> None:
        """Verify the pulse loop calls callAfter with _set_alpha and alpha in range."""
        RecordingOverlay, _ = _make_overlay_module()
        overlay = RecordingOverlay()

        call_count = 0
        alphas: list[float] = []

        def fake_call_after(fn, *args):
            nonlocal call_count
            # Ignore stray calls from leaked threads of other overlay instances
            if getattr(fn, "__self__", None) is not overlay:
                return
            assert getattr(fn, "__name__", None) == "_set_alpha"
            alphas.append(args[0])
            call_count += 1
            if call_count >= 3:
                overlay._pulse_stop.set()

        with patch("whisper_dic.overlay.callAfter", side_effect=fake_call_after):
            overlay._pulse_stop.clear()
            overlay._pulse_loop()

        assert call_count >= 3
        for alpha in alphas:
            assert 0.3 <= alpha <= 1.1  # 0.7 +/- 0.3


# ---------------------------------------------------------------------------
# PreviewOverlay
# ---------------------------------------------------------------------------


class TestPreviewOverlayInit:
    def test_initial_state(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        assert overlay._window is None
        assert overlay._label is None
        assert overlay._status_label is None
        assert overlay._time_label is None
        assert overlay._visible is False
        assert overlay._badges == []
        assert overlay._recording_start == 0.0
        assert overlay._last_text_time == 0.0
        assert overlay._progress_phase == 0
        assert overlay._reduced_motion is False
        assert overlay._high_contrast is False
        assert overlay._font_scale == 1.0

    def test_class_constants(self) -> None:
        _, PreviewOverlay = _make_overlay_module()

        assert PreviewOverlay.MIN_WIDTH == 200
        assert PreviewOverlay.MAX_WIDTH == 500
        assert PreviewOverlay.MAX_HEIGHT == 300
        assert PreviewOverlay.PADDING == 10
        assert PreviewOverlay.CURSOR_OFFSET_Y == 20
        assert PreviewOverlay.FONT_SIZE == 13.0
        assert PreviewOverlay.STATUS_FONT_SIZE == 10.0
        assert PreviewOverlay.FADE_IN_DURATION == 0.15
        assert PreviewOverlay.FADE_OUT_DURATION == 0.20


class TestPreviewOverlayAccessibility:
    def test_configure_accessibility_stores_preferences(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter"):
            overlay.configure_accessibility(reduced_motion=True, high_contrast=True, font_scale=1.5)

        assert overlay._reduced_motion is True
        assert overlay._high_contrast is True
        assert overlay._font_scale == 1.5

    def test_configure_accessibility_clamps_font_scale_low(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter"):
            overlay.configure_accessibility(reduced_motion=False, high_contrast=False, font_scale=0.1)

        assert overlay._font_scale == 0.75

    def test_configure_accessibility_clamps_font_scale_high(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter"):
            overlay.configure_accessibility(reduced_motion=False, high_contrast=False, font_scale=5.0)

        assert overlay._font_scale == 2.0

    def test_configure_accessibility_dispatches_style_to_main_thread(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.configure_accessibility(reduced_motion=False, high_contrast=False, font_scale=1.0)

        mock_call_after.assert_called_once_with(overlay._apply_accessibility_style)

    def test_main_font_size_scales(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._font_scale = 1.5

        assert overlay._main_font_size() == 13.0 * 1.5

    def test_status_font_size_scales(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._font_scale = 2.0

        assert overlay._status_font_size() == 10.0 * 2.0

    def test_apply_accessibility_style_noop_without_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._window = None
        # Should not raise
        overlay._apply_accessibility_style()

    def test_apply_accessibility_style_updates_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._window = MagicMock()
        overlay._label = MagicMock()
        overlay._status_label = MagicMock()
        overlay._time_label = MagicMock()
        overlay._high_contrast = True
        overlay._badges = ["EN"]

        with (
            patch.object(overlay, "_render_badges") as mock_badges,
            patch.object(overlay, "_resize_to_fit") as mock_resize,
        ):
            overlay._apply_accessibility_style()

        overlay._window.setBackgroundColor_.assert_called_once()
        overlay._label.setFont_.assert_called_once()
        overlay._label.setTextColor_.assert_called_once()
        overlay._status_label.setFont_.assert_called_once()
        overlay._time_label.setFont_.assert_called_once()
        overlay._time_label.setTextColor_.assert_called_once()
        mock_badges.assert_called_once()
        mock_resize.assert_called_once()

    def test_background_color_high_contrast(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        from AppKit import NSColor

        overlay = PreviewOverlay()
        overlay._high_contrast = True

        color = overlay._background_color()
        # High contrast should use alpha 0.95
        expected = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.0, 0.0, 0.0, 0.95)
        assert color == expected

    def test_background_color_normal(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        from AppKit import NSColor

        overlay = PreviewOverlay()
        overlay._high_contrast = False

        color = overlay._background_color()
        expected = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.10, 0.85)
        assert color == expected


class TestPreviewOverlayBadges:
    def test_set_badges(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        overlay.set_badges(["EN", "AI Rewrite"])

        assert overlay._badges == ["EN", "AI Rewrite"]

    def test_set_recording_start(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        t = 12345.0

        overlay.set_recording_start(t)

        assert overlay._recording_start == t
        assert overlay._last_text_time == t
        assert overlay._progress_phase == 0

    def test_badge_colors_defined(self) -> None:
        _, PreviewOverlay = _make_overlay_module()

        assert "AI Rewrite" in PreviewOverlay._BADGE_COLORS
        assert "Auto-Send" in PreviewOverlay._BADGE_COLORS

    def test_render_badges_noop_without_status_label(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._status_label = None
        overlay._badges = ["EN"]
        # Should not raise
        overlay._render_badges()

    def test_render_badges_noop_without_badges(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._status_label = MagicMock()
        overlay._badges = []
        # Should not raise, and should not call setAttributedStringValue_
        overlay._render_badges()
        overlay._status_label.setAttributedStringValue_.assert_not_called()


class TestPreviewOverlayShowHide:
    def test_show_dispatches_to_main_thread(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.show("Hello")

        mock_call_after.assert_called_once_with(overlay._show, "Hello")

    def test_show_updates_last_text_time(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        before = time.monotonic()

        with patch("whisper_dic.overlay.callAfter"):
            overlay.show("test")

        assert overlay._last_text_time >= before
        assert overlay._progress_phase == 0

    def test_hide_dispatches_to_main_thread(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter") as mock_call_after:
            overlay.hide()

        mock_call_after.assert_called_once_with(overlay._hide)

    def test_show_internal_calls_ensure_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with (
            patch.object(overlay, "_ensure_window") as mock_ensure,
            patch.object(overlay, "_render_badges"),
            patch.object(overlay, "_update_time_display"),
            patch.object(overlay, "_resize_to_fit"),
            patch.object(overlay, "_position_near_cursor"),
            patch.object(overlay, "_start_cursor_tracking"),
        ):
            overlay._label = MagicMock()
            overlay._window = MagicMock()
            overlay._window.animator.return_value = MagicMock()
            overlay._show("test")

        mock_ensure.assert_called_once()

    def test_show_internal_returns_early_if_no_label(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = None

        with patch.object(overlay, "_ensure_window"):
            # Should not raise
            overlay._show("test")

    def test_show_internal_sets_text_and_renders(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = MagicMock()
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()

        with (
            patch.object(overlay, "_ensure_window"),
            patch.object(overlay, "_render_badges") as mock_badges,
            patch.object(overlay, "_update_time_display") as mock_time,
            patch.object(overlay, "_resize_to_fit") as mock_resize,
            patch.object(overlay, "_position_near_cursor") as mock_pos,
            patch.object(overlay, "_start_cursor_tracking"),
            patch("whisper_dic.overlay.NSAnimationContext"),
        ):
            overlay._show("Hello world")

        overlay._label.setStringValue_.assert_called_once_with("Hello world")
        mock_badges.assert_called_once()
        mock_time.assert_called_once()
        mock_resize.assert_called_once()
        mock_pos.assert_called_once()

    def test_show_internal_fade_in_on_first_show(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = MagicMock()
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()
        overlay._visible = False

        with (
            patch.object(overlay, "_ensure_window"),
            patch.object(overlay, "_render_badges"),
            patch.object(overlay, "_update_time_display"),
            patch.object(overlay, "_resize_to_fit"),
            patch.object(overlay, "_position_near_cursor"),
            patch.object(overlay, "_start_cursor_tracking"),
            patch("whisper_dic.overlay.NSAnimationContext") as mock_anim,
        ):
            overlay._show("test")

        # Should set alpha to 0 before fade-in
        overlay._window.setAlphaValue_.assert_any_call(0.0)
        overlay._window.orderFront_.assert_called_with(None)
        mock_anim.beginGrouping.assert_called_once()
        mock_anim.endGrouping.assert_called_once()
        overlay._window.animator().setAlphaValue_.assert_called_once_with(0.95)

    def test_show_internal_no_fade_on_subsequent_show(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = MagicMock()
        overlay._window = MagicMock()
        overlay._visible = True  # Already visible

        with (
            patch.object(overlay, "_ensure_window"),
            patch.object(overlay, "_render_badges"),
            patch.object(overlay, "_update_time_display"),
            patch.object(overlay, "_resize_to_fit"),
            patch.object(overlay, "_position_near_cursor"),
            patch("whisper_dic.overlay.NSAnimationContext") as mock_anim,
        ):
            overlay._show("update")

        overlay._window.orderFront_.assert_called_once_with(None)
        # No animation grouping for subsequent show
        mock_anim.beginGrouping.assert_not_called()

    def test_show_internal_starts_cursor_tracking_on_first_show(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = MagicMock()
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()
        overlay._visible = False

        with (
            patch.object(overlay, "_ensure_window"),
            patch.object(overlay, "_render_badges"),
            patch.object(overlay, "_update_time_display"),
            patch.object(overlay, "_resize_to_fit"),
            patch.object(overlay, "_position_near_cursor"),
            patch.object(overlay, "_start_cursor_tracking") as mock_track,
            patch("whisper_dic.overlay.NSAnimationContext"),
        ):
            overlay._show("test")

        mock_track.assert_called_once()
        assert overlay._visible is True

    def test_show_internal_fade_in_duration_zero_when_reduced_motion(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = MagicMock()
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()
        overlay._visible = False
        overlay._reduced_motion = True

        mock_context = MagicMock()
        with (
            patch.object(overlay, "_ensure_window"),
            patch.object(overlay, "_render_badges"),
            patch.object(overlay, "_update_time_display"),
            patch.object(overlay, "_resize_to_fit"),
            patch.object(overlay, "_position_near_cursor"),
            patch.object(overlay, "_start_cursor_tracking"),
            patch("whisper_dic.overlay.NSAnimationContext") as mock_anim,
        ):
            mock_anim.currentContext.return_value = mock_context
            overlay._show("test")

        mock_context.setDuration_.assert_called_once_with(0.0)

    def test_hide_internal_resets_state(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = True
        overlay._recording_start = 100.0
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()

        with (
            patch.object(overlay, "_stop_cursor_tracking") as mock_stop,
            patch("whisper_dic.overlay.NSAnimationContext"),
            patch("whisper_dic.overlay.callAfter"),
        ):
            overlay._hide()

        assert overlay._visible is False
        assert overlay._recording_start == 0.0
        mock_stop.assert_called_once()

    def test_hide_internal_fades_out(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = True
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()

        mock_context = MagicMock()
        with (
            patch.object(overlay, "_stop_cursor_tracking"),
            patch("whisper_dic.overlay.NSAnimationContext") as mock_anim,
            patch("whisper_dic.overlay.callAfter") as mock_call_after,
        ):
            mock_anim.currentContext.return_value = mock_context
            overlay._hide()

        mock_anim.beginGrouping.assert_called_once()
        mock_anim.endGrouping.assert_called_once()
        overlay._window.animator().setAlphaValue_.assert_called_once_with(0.0)
        mock_call_after.assert_called_once_with(overlay._deferred_order_out)

    def test_hide_internal_noop_without_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = True
        overlay._window = None

        with patch.object(overlay, "_stop_cursor_tracking"):
            # Should not raise
            overlay._hide()

        assert overlay._visible is False

    def test_hide_internal_duration_zero_when_reduced_motion(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = True
        overlay._window = MagicMock()
        overlay._window.animator.return_value = MagicMock()
        overlay._reduced_motion = True

        mock_context = MagicMock()
        with (
            patch.object(overlay, "_stop_cursor_tracking"),
            patch("whisper_dic.overlay.NSAnimationContext") as mock_anim,
            patch("whisper_dic.overlay.callAfter"),
        ):
            mock_anim.currentContext.return_value = mock_context
            overlay._hide()

        mock_context.setDuration_.assert_called_once_with(0.0)

    def test_deferred_order_out_hides_when_not_visible(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = False
        overlay._window = MagicMock()

        overlay._deferred_order_out()

        overlay._window.orderOut_.assert_called_once_with(None)

    def test_deferred_order_out_noop_when_visible(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = True
        overlay._window = MagicMock()

        overlay._deferred_order_out()

        overlay._window.orderOut_.assert_not_called()

    def test_deferred_order_out_noop_without_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._visible = False
        overlay._window = None
        # Should not raise
        overlay._deferred_order_out()


class TestPreviewOverlayCursorTracking:
    def test_start_cursor_tracking_creates_thread(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with patch("whisper_dic.overlay.callAfter"):
            overlay._start_cursor_tracking()

            assert overlay._tracking_thread is not None
            assert overlay._tracking_thread.daemon is True
            assert overlay._tracking_thread.name == "cursor-track"

            # Clean up while patch is still active
            thread = overlay._tracking_thread
            overlay._stop_cursor_tracking()
            thread.join(timeout=1.0)

    def test_stop_cursor_tracking_sets_event_and_joins(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        mock_thread = MagicMock()
        overlay._tracking_thread = mock_thread

        overlay._stop_cursor_tracking()

        assert overlay._tracking_stop.is_set()
        mock_thread.join.assert_called_once_with(timeout=0.5)
        assert overlay._tracking_thread is None

    def test_stop_cursor_tracking_noop_without_thread(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._tracking_thread = None

        # Should not raise
        overlay._stop_cursor_tracking()
        assert overlay._tracking_stop.is_set()

    def test_track_tick_calls_position_and_time(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        with (
            patch.object(overlay, "_position_near_cursor") as mock_pos,
            patch.object(overlay, "_update_time_display") as mock_time,
        ):
            overlay._track_tick()

        mock_pos.assert_called_once()
        mock_time.assert_called_once()

    def test_track_cursor_loop_dispatches_tick(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()

        call_count = 0

        def fake_call_after(fn, *args):
            nonlocal call_count
            # Ignore stray calls from leaked threads of other overlay instances
            if fn != overlay._track_tick:
                return
            call_count += 1
            if call_count >= 3:
                overlay._tracking_stop.set()

        with patch("whisper_dic.overlay.callAfter", side_effect=fake_call_after):
            overlay._tracking_stop.clear()
            overlay._track_cursor_loop()

        assert call_count >= 3


class TestPreviewOverlayTimeDisplay:
    def test_update_time_display_noop_without_time_label(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._time_label = None
        overlay._recording_start = 1.0
        # Should not raise
        overlay._update_time_display()

    def test_update_time_display_noop_when_no_recording_start(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._time_label = MagicMock()
        overlay._recording_start = 0.0
        # Should not raise, and should not update label
        overlay._update_time_display()
        overlay._time_label.setStringValue_.assert_not_called()

    def test_update_time_display_formats_elapsed(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._time_label = MagicMock()

        now = time.monotonic()
        overlay._recording_start = now - 65  # 1 minute 5 seconds
        overlay._last_text_time = now  # text just arrived, no dots

        overlay._update_time_display()

        val = overlay._time_label.setStringValue_.call_args.args[0]
        assert "1:05" in val

    def test_update_time_display_shows_dots_after_delay(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._time_label = MagicMock()

        now = time.monotonic()
        overlay._recording_start = now - 10
        overlay._last_text_time = now - 2.0  # text was 2 seconds ago

        overlay._update_time_display()

        val = overlay._time_label.setStringValue_.call_args.args[0]
        assert "." in val  # has progress dots


class TestPreviewOverlayPositioning:
    def test_position_near_cursor_noop_without_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._window = None
        # Should not raise
        overlay._position_near_cursor()

    def test_resize_to_fit_noop_without_label(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = None
        overlay._window = MagicMock()
        # Should not raise
        overlay._resize_to_fit()

    def test_resize_to_fit_noop_without_window(self) -> None:
        _, PreviewOverlay = _make_overlay_module()
        overlay = PreviewOverlay()
        overlay._label = MagicMock()
        overlay._window = None
        # Should not raise
        overlay._resize_to_fit()
