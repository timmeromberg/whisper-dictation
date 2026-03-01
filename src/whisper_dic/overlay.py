"""Recording indicator — small floating dot near the menu bar."""

from __future__ import annotations

import threading
from typing import Any

from AppKit import (
    NSBezierPath,
    NSColor,
    NSEvent,
    NSFloatingWindowLevel,
    NSFont,
    NSMakeRect,
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

    def __init__(self) -> None:
        self._window: NSWindow | None = None
        self._dot: _DotView | None = None
        self._lock = threading.Lock()

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
        """Show a red dot (recording). Safe to call from any thread."""
        callAfter(self._show, NSColor.redColor())

    def show_transcribing(self) -> None:
        """Show an orange dot (transcribing). Safe to call from any thread."""
        callAfter(self._show, NSColor.orangeColor())

    def hide(self) -> None:
        """Hide the dot. Safe to call from any thread."""
        callAfter(self._hide)

    def _show(self, color: Any) -> None:
        """Main-thread: create window if needed, set color, show."""
        self._ensure_window()
        if self._dot is None:
            return
        self._dot._color = color
        self._dot.setNeedsDisplay_(True)
        if self._window is not None:
            self._window.orderFront_(None)

    def _hide(self) -> None:
        """Main-thread: hide window."""
        if self._window is not None:
            self._window.orderOut_(None)


class PreviewOverlay:
    """Floating translucent panel showing live transcription preview near the cursor."""

    WIDTH = 400
    HEIGHT = 60
    PADDING = 8
    CURSOR_OFFSET_Y = 20  # pixels above the cursor
    MAX_DISPLAY_CHARS = 120
    _TRACK_INTERVAL = 0.08  # seconds between cursor position updates

    def __init__(self) -> None:
        self._window: NSWindow | None = None
        self._label: NSTextField | None = None
        self._tracking_stop = threading.Event()
        self._tracking_thread: threading.Thread | None = None
        self._visible = False

    def show(self, text: str) -> None:
        """Show or update preview text near cursor. Safe to call from any thread."""
        callAfter(self._show, text)

    def hide(self) -> None:
        """Hide the preview panel. Safe to call from any thread."""
        callAfter(self._hide)

    def _ensure_window(self) -> None:
        """Create the preview window. MUST be called on main thread."""
        if self._window is not None:
            return

        # Initial rect — will be repositioned in _show
        rect = NSMakeRect(0, 0, self.WIDTH, self.HEIGHT)

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
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.1, 0.8)
        )
        window.setAlphaValue_(0.95)
        window.setHasShadow_(True)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(10.0)
        content.layer().setMasksToBounds_(True)

        label_rect = NSMakeRect(
            self.PADDING, self.PADDING,
            self.WIDTH - 2 * self.PADDING,
            self.HEIGHT - 2 * self.PADDING,
        )
        label = NSTextField.alloc().initWithFrame_(label_rect)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setTextColor_(NSColor.whiteColor())
        label.setFont_(NSFont.systemFontOfSize_(13.0))
        label.setStringValue_("")
        label.setMaximumNumberOfLines_(2)
        content.addSubview_(label)

        self._window = window
        self._label = label

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

        # Center horizontally on cursor, place above cursor
        x = mouse.x - self.WIDTH / 2
        y = mouse.y + self.CURSOR_OFFSET_Y

        # If window would go above visible area, place below cursor instead
        if y + self.HEIGHT > vy + vh:
            y = mouse.y - self.HEIGHT - self.CURSOR_OFFSET_Y

        # Clamp to visible screen bounds
        x = max(vx, min(x, vx + vw - self.WIDTH))
        y = max(vy, min(y, vy + vh - self.HEIGHT))

        self._window.setFrameOrigin_((x, y))

    def _show(self, text: str) -> None:
        """Main-thread: create window if needed, update text, show near cursor."""
        self._ensure_window()
        if self._label is None:
            return

        display = text
        if len(display) > self.MAX_DISPLAY_CHARS:
            display = "..." + display[-(self.MAX_DISPLAY_CHARS - 3):]
        self._label.setStringValue_(display)

        self._position_near_cursor()
        if self._window is not None:
            self._window.orderFront_(None)

        if not self._visible:
            self._visible = True
            self._start_cursor_tracking()

    def _hide(self) -> None:
        """Main-thread: hide window."""
        self._visible = False
        self._stop_cursor_tracking()
        if self._window is not None:
            self._window.orderOut_(None)

    def _start_cursor_tracking(self) -> None:
        """Start a background thread that repositions the window near the cursor."""
        self._tracking_stop.clear()
        self._tracking_thread = threading.Thread(
            target=self._track_cursor_loop, daemon=True, name="cursor-track",
        )
        self._tracking_thread.start()

    def _track_cursor_loop(self) -> None:
        """Periodically dispatch cursor reposition to main thread."""
        while not self._tracking_stop.wait(self._TRACK_INTERVAL):
            callAfter(self._position_near_cursor)

    def _stop_cursor_tracking(self) -> None:
        """Stop the cursor tracking thread."""
        self._tracking_stop.set()
        if self._tracking_thread is not None:
            self._tracking_thread.join(timeout=0.5)
            self._tracking_thread = None
