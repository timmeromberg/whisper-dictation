"""App-context resolution: detect frontmost app category for context-aware rewriting."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import dataclass

# Category constants
CODING = "coding"
CHAT = "chat"
EMAIL = "email"
WRITING = "writing"
BROWSER = "browser"

CATEGORIES = [CODING, CHAT, EMAIL, WRITING, BROWSER]

# --- App-to-category mappings (hardcoded, not user-configurable) ---

_MACOS_APP_CATEGORIES: dict[str, str] = {
    # coding — terminals
    "com.apple.Terminal": CODING,
    "com.googlecode.iterm2": CODING,
    "net.kovidgoyal.kitty": CODING,
    "io.alacritty": CODING,
    "com.github.wez.wezterm": CODING,
    "dev.warp.Warp-Stable": CODING,
    "co.zeit.hyper": CODING,
    # coding — AI IDEs and editors
    "com.microsoft.VSCode": CODING,
    "com.todesktop.230313mzl4w4u92": CODING,  # Cursor
    "com.codeium.windsurf": CODING,
    "dev.zed.Zed": CODING,
    "com.sublimetext.4": CODING,
    "org.vim.MacVim": CODING,
    "com.panic.Nova": CODING,
    # coding — JetBrains
    "com.jetbrains.intellij": CODING,
    "com.jetbrains.intellij.ce": CODING,
    "com.jetbrains.pycharm": CODING,
    "com.jetbrains.pycharm.ce": CODING,
    "com.jetbrains.WebStorm": CODING,
    "com.jetbrains.CLion": CODING,
    "com.jetbrains.goland": CODING,
    "com.jetbrains.rider": CODING,
    "com.jetbrains.rubymine": CODING,
    "com.jetbrains.PhpStorm": CODING,
    "com.jetbrains.datagrip": CODING,
    # chat
    "com.tinyspeck.slackmacgap": CHAT,
    "com.hnc.Discord": CHAT,
    "com.microsoft.teams2": CHAT,
    "com.apple.MobileSMS": CHAT,
    "org.whispersystems.signal-desktop": CHAT,
    "ph.telegra.Telegraph": CHAT,
    # email
    "com.apple.mail": EMAIL,
    "com.microsoft.Outlook": EMAIL,
    "com.readdle.smartemail.macos": EMAIL,
    "com.superhuman.mail": EMAIL,
    # writing
    "com.apple.Notes": WRITING,
    "md.obsidian": WRITING,
    "notion.id": WRITING,
    "com.microsoft.Word": WRITING,
    "com.apple.iWork.Pages": WRITING,
    "net.shinyfrog.bear": WRITING,
    "com.ulyssesapp.mac": WRITING,
    # browser
    "com.apple.Safari": BROWSER,
    "com.google.Chrome": BROWSER,
    "org.mozilla.firefox": BROWSER,
    "company.thebrowser.Browser": BROWSER,  # Arc
    "com.brave.Browser": BROWSER,
    "com.microsoft.edgemac": BROWSER,
    "com.vivaldi.Vivaldi": BROWSER,
    "com.operasoftware.Opera": BROWSER,
}

_WINDOWS_APP_CATEGORIES: dict[str, str] = {
    # coding — terminals
    "cmd.exe": CODING,
    "powershell.exe": CODING,
    "pwsh.exe": CODING,
    "windowsterminal.exe": CODING,
    "wt.exe": CODING,
    # coding — editors and IDEs
    "code.exe": CODING,
    "cursor.exe": CODING,
    "windsurf.exe": CODING,
    "zed.exe": CODING,
    "sublime_text.exe": CODING,
    # coding — JetBrains
    "idea64.exe": CODING,
    "pycharm64.exe": CODING,
    "webstorm64.exe": CODING,
    "clion64.exe": CODING,
    "goland64.exe": CODING,
    "rider64.exe": CODING,
    "rubymine64.exe": CODING,
    "phpstorm64.exe": CODING,
    "datagrip64.exe": CODING,
    # chat
    "slack.exe": CHAT,
    "discord.exe": CHAT,
    "teams.exe": CHAT,
    "signal.exe": CHAT,
    "telegram.exe": CHAT,
    # email
    "outlook.exe": EMAIL,
    # writing
    "winword.exe": WRITING,
    "obsidian.exe": WRITING,
    "notion.exe": WRITING,
    # browser
    "chrome.exe": BROWSER,
    "firefox.exe": BROWSER,
    "msedge.exe": BROWSER,
    "brave.exe": BROWSER,
    "vivaldi.exe": BROWSER,
    "opera.exe": BROWSER,
}

_LINUX_APP_CATEGORIES: dict[str, str] = {
    # coding — terminals
    "gnome-terminal-server": CODING,
    "konsole": CODING,
    "kitty": CODING,
    "alacritty": CODING,
    "wezterm": CODING,
    "wezterm-gui": CODING,
    "tilix": CODING,
    "xfce4-terminal": CODING,
    "xterm": CODING,
    # coding — editors and IDEs
    "code": CODING,
    "code-oss": CODING,
    "codium": CODING,
    "cursor": CODING,
    "windsurf": CODING,
    "zed": CODING,
    "idea": CODING,
    "pycharm": CODING,
    "webstorm": CODING,
    "clion": CODING,
    "goland": CODING,
    "rider": CODING,
    "rubymine": CODING,
    "phpstorm": CODING,
    "datagrip": CODING,
    # chat
    "slack": CHAT,
    "discord": CHAT,
    "teams-for-linux": CHAT,
    "teams": CHAT,
    "signal-desktop": CHAT,
    "telegram-desktop": CHAT,
    "telegram": CHAT,
    # email
    "thunderbird": EMAIL,
    "evolution": EMAIL,
    "geary": EMAIL,
    "mailspring": EMAIL,
    # writing
    "obsidian": WRITING,
    "notion": WRITING,
    "libreoffice-writer": WRITING,
    "writer": WRITING,
    # browser
    "firefox": BROWSER,
    "google-chrome": BROWSER,
    "chrome": BROWSER,
    "chromium": BROWSER,
    "brave-browser": BROWSER,
    "microsoft-edge": BROWSER,
    "microsoft-edge-stable": BROWSER,
    "vivaldi-stable": BROWSER,
    "opera": BROWSER,
}


@dataclass(frozen=True)
class RewriteContext:
    """Resolved rewrite context for a single dictation."""

    category: str | None  # "coding", "chat", etc., or None for global fallback
    app_id: str  # raw bundle ID / exe name


def category_for_app(app_id: str) -> str | None:
    """Return the category name for a given app ID, or None if unrecognized."""
    if not app_id:
        return None
    if sys.platform == "darwin":
        return _MACOS_APP_CATEGORIES.get(app_id)
    if sys.platform == "win32":
        return _WINDOWS_APP_CATEGORIES.get(app_id.lower())
    if sys.platform.startswith("linux"):
        return _LINUX_APP_CATEGORIES.get(app_id.lower())
    return None


def resolve_context(
    app_id: str,
    context_configs: Mapping[str, object],
) -> RewriteContext:
    """Resolve the rewrite context for a frontmost app.

    Args:
        app_id: Bundle ID (macOS) or exe name (Windows) of the frontmost app.
        context_configs: Dict of category -> ContextConfig (must have `.enabled` attr).

    Returns:
        RewriteContext with category set if the app matches a known, enabled category.
    """
    category = category_for_app(app_id)

    if category is not None and category in context_configs:
        cfg = context_configs[category]
        if getattr(cfg, "enabled", True):
            return RewriteContext(category=category, app_id=app_id)

    return RewriteContext(category=None, app_id=app_id)
