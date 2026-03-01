"""Recording indicator — small floating dot near the menu bar."""

from __future__ import annotations

import math
import threading
import time
from typing import Any

from AppKit import (
    NSAnimationContext,
    NSAttributedString,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSMakeSize,
    NSRightTextAlignment,
    NSScreen,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskBorderless,
)
from PyObjCTools.AppHelper import callAfter


class _DotView(NSView):
    """Custom view that draws a colored circle."""

    _color = NSColor.redColor()

    def drawRect_(self, rect):  # noqa: N802 — AppKit naming convention
        self._color.set()
        NSBezierPath.bezierPathWithOvalInRect_(self.bounds()).fill()


class RecordingOverlay:
    """Floating dot indicator for recording/transcribing state."""

    DOT_SIZE = 12
    _PULSE_INTERVAL = 0.08  # match tracking interval for smooth updates
    _PULSE_SPEED = 2.5  # cycles per second

    def __init__(self) -> None:
        self._window: NSWindow | None = None
        self._dot: _DotView | None = None
        self._lock = threading.Lock()
        self._pulsing = False
        self._pulse_stop = threading.Event()
        self._pulse_thread: threading.Thread | None = None

    def _ensure_window(self) -> None:
        """Create the window. MUST be called on main thread."""
        if self._window is not None:
            return

        screen = NSScreen.mainScreen()
        if screen is None:
            return
        frame = screen.frame()

        # Position: near top-right, offset from menu bar area
        x = frame.size.width - 60
        y = frame.size.height - 16
        rect = NSMakeRect(x, y, self.DOT_SIZE, self.DOT_SIZE)

        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless,
            2,  # NSBackingStoreBuffered
            False,
        )
        window.setLevel_(NSFloatingWindowLevel)
        window.setIgnoresMouseEvents_(True)
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setAlphaValue_(0.85)
        window.setHasShadow_(False)

        dot = _DotView.alloc().initWithFrame_(NSMakeRect(0, 0, self.DOT_SIZE, self.DOT_SIZE))
        window.setContentView_(dot)

        self._window = window
        self._dot = dot

    def show_recording(self) -> None:
        """Show a pulsing red dot (recording). Safe to call from any thread."""
        callAfter(self._show, NSColor.redColor(), True)

    def show_transcribing(self) -> None:
        """Show a static orange dot (transcribing). Safe to call from any thread."""
        callAfter(self._show, NSColor.orangeColor(), False)

    def hide(self) -> None:
        """Hide the dot. Safe to call from any thread."""
        self._stop_pulse()
        callAfter(self._hide)

    def _show(self, color: Any, pulse: bool) -> None:
        """Main-thread: create window if needed, set color, show."""
        self._ensure_window()
        if self._dot is None:
            return
        self._dot._color = color
        self._dot.setNeedsDisplay_(True)
        if self._window is not None:
            self._window.setAlphaValue_(0.85)
            self._window.orderFront_(None)
        if pulse:
            self._start_pulse()
        else:
            self._stop_pulse()

    def _hide(self) -> None:
        """Main-thread: hide window."""
        if self._window is not None:
            self._window.orderOut_(None)

    def _start_pulse(self) -> None:
        """Start the pulsing animation thread."""
        if self._pulsing:
            return
        self._pulsing = True
        self._pulse_stop.clear()
        self._pulse_thread = threading.Thread(
            target=self._pulse_loop, daemon=True, name="dot-pulse",
        )
        self._pulse_thread.start()

    def _stop_pulse(self) -> None:
        """Stop the pulsing animation thread."""
        self._pulsing = False
        self._pulse_stop.set()
        if self._pulse_thread is not None:
            self._pulse_thread.join(timeout=0.5)
            self._pulse_thread = None

    def _pulse_loop(self) -> None:
        """Background thread: cycle alpha between 0.4 and 1.0."""
        while not self._pulse_stop.wait(self._PULSE_INTERVAL):
            t = time.monotonic()
            # Sine wave oscillation: 0.4 .. 1.0
            phase = math.sin(t * self._PULSE_SPEED * 2 * math.pi)
            alpha = 0.7 + 0.3 * phase  # range: 0.4 to 1.0
            callAfter(self._set_alpha, alpha)

    def _set_alpha(self, alpha: float) -> None:
        """Main-thread: update window alpha."""
        if self._window is not None and self._pulsing:
            self._window.setAlphaValue_(alpha)


class _LevelBarView(NSView):
    """Thin horizontal bar showing current microphone level."""

    _level: float = 0.0

    def drawRect_(self, rect):  # noqa: N802 — AppKit naming convention
        bounds = self.bounds()
        w = bounds.size.width
        h = bounds.size.height

        # Background track
        NSColor.colorWithCalibratedWhite_alpha_(0.2, 0.6).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(bounds, h / 2, h / 2).fill()

        if self._level <= 0.01:
            return

        # Filled portion
        fill_w = max(h, w * self._level)  # at least a circle
        fill_rect = NSMakeRect(0, 0, fill_w, h)

        # Color: green → yellow → red
        level = self._level
        if level < 0.5:
            r, g = level * 2 * 0.9, 0.75
        else:
            r, g = 0.9, 0.75 * (1.0 - (level - 0.5) * 2)
        NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, 0.15, 0.9).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(fill_rect, h / 2, h / 2).fill()


class PreviewOverlay:
    """Floating translucent panel showing live transcription preview near the cursor."""

    MIN_WIDTH = 200
    MAX_WIDTH = 500
    MAX_HEIGHT = 300
    PADDING = 10
    STATUS_HEIGHT = 18
    STATUS_GAP = 4
    CURSOR_OFFSET_Y = 20
    FONT_SIZE = 13.0
    STATUS_FONT_SIZE = 10.0
    LEVEL_BAR_HEIGHT = 3
    LEVEL_BAR_GAP = 4
    FADE_IN_DURATION = 0.15
    FADE_OUT_DURATION = 0.20
    _TRACK_INTERVAL = 0.08

    def __init__(self) -> None:
        self._window: NSWindow | None = None
        self._label: NSTextField | None = None
        self._status_label: NSTextField | None = None
        self._time_label: NSTextField | None = None
        self._tracking_stop = threading.Event()
        self._tracking_thread: threading.Thread | None = None
        self._visible = False
        self._badges: list[str] = []
        self._level_bar: _LevelBarView | None = None
        self._recording_start: float = 0.0
        self._last_text_time: float = 0.0
        self._progress_phase = 0
        self._show_level = False

    def set_badges(self, badges: list[str]) -> None:
        """Set status badges (e.g. ["EN", "AI Rewrite", "Auto-Send"]). Thread-safe."""
        self._badges = badges

    def set_recording_start(self, t: float) -> None:
        """Set the recording start timestamp for elapsed time display."""
        self._recording_start = t
        self._last_text_time = t
        self._progress_phase = 0

    def set_level(self, peak: float) -> None:
        """Update the mic level bar (0.0 to 1.0). Safe to call from any thread."""
        callAfter(self._update_level, peak)

    def show_level_bar(self, visible: bool) -> None:
        """Show or hide the level bar. Safe to call from any thread."""
        self._show_level = visible
        if not visible:
            callAfter(self._update_level, 0.0)

    def show(self, text: str) -> None:
        """Show or update preview text near cursor. Safe to call from any thread."""
        self._last_text_time = time.monotonic()
        self._progress_phase = 0
        callAfter(self._show, text)

    def hide(self) -> None:
        """Hide the preview panel. Safe to call from any thread."""
        callAfter(self._hide)

    def _ensure_window(self) -> None:
        """Create the preview window. MUST be called on main thread."""
        if self._window is not None:
            return

        rect = NSMakeRect(0, 0, self.MAX_WIDTH, 40)

        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless,
            2,  # NSBackingStoreBuffered
            False,
        )
        window.setLevel_(NSFloatingWindowLevel)
        window.setIgnoresMouseEvents_(True)
        window.setOpaque_(False)
        window.setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.10, 0.85)
        )
        window.setAlphaValue_(0.0)  # start invisible for fade-in
        window.setHasShadow_(True)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(10.0)
        content.layer().setMasksToBounds_(True)

        # Status badges line (bottom)
        status_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(self.PADDING, self.PADDING, self.MAX_WIDTH - 2 * self.PADDING, self.STATUS_HEIGHT)
        )
        status_label.setEditable_(False)
        status_label.setSelectable_(False)
        status_label.setBezeled_(False)
        status_label.setDrawsBackground_(False)
        status_label.setFont_(NSFont.systemFontOfSize_(self.STATUS_FONT_SIZE))
        status_label.setStringValue_("")
        status_label.setMaximumNumberOfLines_(1)
        content.addSubview_(status_label)

        # Main text label (above status)
        label_y = self.PADDING + self.STATUS_HEIGHT + self.STATUS_GAP
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(self.PADDING, label_y, self.MAX_WIDTH - 2 * self.PADDING, 24)
        )
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setTextColor_(NSColor.whiteColor())
        label.setFont_(NSFont.systemFontOfSize_(self.FONT_SIZE))
        label.setStringValue_("")
        label.setMaximumNumberOfLines_(0)
        label.setPreferredMaxLayoutWidth_(self.MAX_WIDTH - 2 * self.PADDING)
        content.addSubview_(label)

        # Elapsed time + progress indicator (right-aligned, same row as badges)
        time_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(self.PADDING, self.PADDING, self.MAX_WIDTH - 2 * self.PADDING, self.STATUS_HEIGHT)
        )
        time_label.setEditable_(False)
        time_label.setSelectable_(False)
        time_label.setBezeled_(False)
        time_label.setDrawsBackground_(False)
        time_label.setTextColor_(
            NSColor.colorWithCalibratedWhite_alpha_(0.5, 1.0)
        )
        time_label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(self.STATUS_FONT_SIZE, 0.0))
        time_label.setAlignment_(NSRightTextAlignment)
        time_label.setStringValue_("")
        time_label.setMaximumNumberOfLines_(1)
        content.addSubview_(time_label)

        # Mic level bar (just below time label)
        level_bar = _LevelBarView.alloc().initWithFrame_(
            NSMakeRect(self.PADDING, 0, self.MAX_WIDTH - 2 * self.PADDING, self.LEVEL_BAR_HEIGHT)
        )
        level_bar.setHidden_(True)
        content.addSubview_(level_bar)

        self._window = window
        self._label = label
        self._status_label = status_label
        self._time_label = time_label
        self._level_bar = level_bar

    def _resize_to_fit(self) -> None:
        """Resize window to fit label content. MUST be called on main thread."""
        if self._label is None or self._window is None:
            return

        max_label_w = self.MAX_WIDTH - 2 * self.PADDING
        has_bottom = (self._badges and self._status_label is not None) or self._recording_start > 0
        bottom_total = (self.STATUS_HEIGHT + self.STATUS_GAP) if has_bottom else 0
        max_text_h = self.MAX_HEIGHT - 2 * self.PADDING - bottom_total

        ideal = self._label.cell().cellSizeForBounds_(
            NSMakeRect(0, 0, max_label_w, max_text_h)
        )
        label_w = max(self.MIN_WIDTH - 2 * self.PADDING, min(ideal.width, max_label_w))
        label_h = min(ideal.height, max_text_h)

        win_w = label_w + 2 * self.PADDING
        win_h = label_h + 2 * self.PADDING + bottom_total

        # Bottom row: badges (left) + time (right) on the same line
        if has_bottom:
            if self._status_label is not None:
                self._status_label.setFrame_(
                    NSMakeRect(self.PADDING, self.PADDING, label_w, self.STATUS_HEIGHT)
                )
                self._status_label.setHidden_(not self._badges)
            if self._time_label is not None:
                self._time_label.setFrame_(
                    NSMakeRect(self.PADDING, self.PADDING, label_w, self.STATUS_HEIGHT)
                )
                self._time_label.setHidden_(False)
            label_y = self.PADDING + self.STATUS_HEIGHT + self.STATUS_GAP
        else:
            if self._status_label is not None:
                self._status_label.setHidden_(True)
            if self._time_label is not None:
                self._time_label.setHidden_(True)
            label_y = self.PADDING

        self._label.setFrame_(NSMakeRect(self.PADDING, label_y, label_w, label_h))

        # Level bar sits just above the text
        has_level = self._show_level and self._level_bar is not None
        if self._level_bar is not None:
            if has_level:
                level_y = win_h - self.PADDING - self.LEVEL_BAR_HEIGHT
                self._level_bar.setFrame_(
                    NSMakeRect(self.PADDING, level_y, label_w, self.LEVEL_BAR_HEIGHT)
                )
                self._level_bar.setHidden_(False)
            else:
                self._level_bar.setHidden_(True)

        frame = self._window.frame()
        frame.size = NSMakeSize(win_w, win_h)
        self._window.setFrame_display_(frame, True)

    def _position_near_cursor(self) -> None:
        """Reposition window near the mouse cursor, clamped to screen."""
        if self._window is None:
            return

        mouse = NSEvent.mouseLocation()
        screen = NSScreen.mainScreen()
        if screen is None:
            return

        visible = screen.visibleFrame()
        vx, vy = visible.origin.x, visible.origin.y
        vw, vh = visible.size.width, visible.size.height

        win_frame = self._window.frame()
        w = win_frame.size.width
        h = win_frame.size.height

        x = mouse.x - w / 2
        y = mouse.y + self.CURSOR_OFFSET_Y

        if y + h > vy + vh:
            y = mouse.y - h - self.CURSOR_OFFSET_Y

        x = max(vx, min(x, vx + vw - w))
        y = max(vy, min(y, vy + vh - h))

        self._window.setFrameOrigin_((x, y))

    def _update_time_display(self) -> None:
        """Update elapsed time and progress indicator. MUST be called on main thread."""
        if self._time_label is None or self._recording_start <= 0:
            return

        now = time.monotonic()
        elapsed = now - self._recording_start
        minutes = int(elapsed) // 60
        seconds = int(elapsed) % 60
        time_str = f"{minutes}:{seconds:02d}"

        # Progress dots cycle every 0.4s since last text update
        since_text = now - self._last_text_time
        if since_text > 0.8:
            dots = "." * (1 + (int(since_text / 0.4) % 3))
            time_str = f"{dots}  {time_str}"

        self._time_label.setStringValue_(time_str)

    _BADGE_COLORS: dict[str, tuple[float, float, float]] = {
        "AI Rewrite": (0.55, 0.36, 0.95),
        "Auto-Send": (0.20, 0.70, 0.45),
    }
    _BADGE_DEFAULT_COLOR = (0.45, 0.55, 0.65)

    def _render_badges(self) -> None:
        """Update the status label with colored badge text."""
        if self._status_label is None or not self._badges:
            return

        font = NSFont.boldSystemFontOfSize_(self.STATUS_FONT_SIZE)
        parts: list[Any] = []
        for i, badge in enumerate(self._badges):
            r, g, b = self._BADGE_COLORS.get(badge, self._BADGE_DEFAULT_COLOR)
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)
            attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
            part = NSAttributedString.alloc().initWithString_attributes_(badge, attrs)
            parts.append(part)
            if i < len(self._badges) - 1:
                sep_color = NSColor.colorWithCalibratedWhite_alpha_(0.4, 1.0)
                sep_attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: sep_color}
                sep = NSAttributedString.alloc().initWithString_attributes_("  \u00b7  ", sep_attrs)
                parts.append(sep)

        combined = parts[0].mutableCopy()
        for part in parts[1:]:
            combined.appendAttributedString_(part)
        self._status_label.setAttributedStringValue_(combined)

    def _show(self, text: str) -> None:
        """Main-thread: create window if needed, update text, show near cursor."""
        self._ensure_window()
        if self._label is None:
            return

        self._label.setStringValue_(text)
        self._render_badges()
        self._update_time_display()
        self._resize_to_fit()
        self._position_near_cursor()

        if self._window is not None:
            if not self._visible:
                # Fade in
                self._window.setAlphaValue_(0.0)
                self._window.orderFront_(None)
                NSAnimationContext.beginGrouping()
                NSAnimationContext.currentContext().setDuration_(self.FADE_IN_DURATION)
                self._window.animator().setAlphaValue_(0.95)
                NSAnimationContext.endGrouping()
            else:
                self._window.orderFront_(None)

        if not self._visible:
            self._visible = True
            self._start_cursor_tracking()

    def _hide(self) -> None:
        """Main-thread: fade out then hide window."""
        self._visible = False
        self._recording_start = 0.0
        self._stop_cursor_tracking()
        if self._window is not None:
            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(self.FADE_OUT_DURATION)
            self._window.animator().setAlphaValue_(0.0)
            NSAnimationContext.endGrouping()
            # Schedule orderOut after animation completes
            callAfter(self._deferred_order_out)

    def _deferred_order_out(self) -> None:
        """Hide window after fade-out animation. MUST be called on main thread."""
        if not self._visible and self._window is not None:
            self._window.orderOut_(None)

    def _update_level(self, peak: float) -> None:
        """Main-thread: update level bar."""
        if self._level_bar is None:
            return
        self._level_bar._level = peak
        self._level_bar.setNeedsDisplay_(True)

    def _start_cursor_tracking(self) -> None:
        """Start a background thread that repositions the window near the cursor."""
        self._tracking_stop.clear()
        self._tracking_thread = threading.Thread(
            target=self._track_cursor_loop, daemon=True, name="cursor-track",
        )
        self._tracking_thread.start()

    def _track_cursor_loop(self) -> None:
        """Periodically dispatch cursor reposition and time update to main thread."""
        while not self._tracking_stop.wait(self._TRACK_INTERVAL):
            callAfter(self._track_tick)

    def _track_tick(self) -> None:
        """Main-thread: reposition and update time."""
        self._position_near_cursor()
        self._update_time_display()

    def _stop_cursor_tracking(self) -> None:
        """Stop the cursor tracking thread."""
        self._tracking_stop.set()
        if self._tracking_thread is not None:
            self._tracking_thread.join(timeout=0.5)
            self._tracking_thread = None
