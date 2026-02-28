"""Recording indicator — small floating dot near the menu bar."""

from __future__ import annotations

import threading
from typing import Any

from AppKit import (
    NSBezierPath,
    NSColor,
    NSFloatingWindowLevel,
    NSMakeRect,
    NSScreen,
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
