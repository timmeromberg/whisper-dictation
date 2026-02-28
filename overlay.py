"""Recording indicator — small floating dot near the menu bar."""

from __future__ import annotations

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
from objc import python_method


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

    def _ensure_window(self) -> None:
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

    @python_method
    def show_recording(self) -> None:
        """Show a red dot (recording)."""
        self._ensure_window()
        if self._dot is None:
            return
        self._dot._color = NSColor.redColor()
        self._dot.setNeedsDisplay_(True)
        self._window.orderFront_(None)

    @python_method
    def show_transcribing(self) -> None:
        """Show an orange dot (transcribing)."""
        self._ensure_window()
        if self._dot is None:
            return
        self._dot._color = NSColor.orangeColor()
        self._dot.setNeedsDisplay_(True)
        self._window.orderFront_(None)

    @python_method
    def hide(self) -> None:
        """Hide the dot."""
        if self._window is not None:
            self._window.orderOut_(None)
