"""
pnut — Theme Engine
Minimalist, terminal-friendly theme engine.
Maintains natural terminal background (-1) for transparency and ricing compatibility.
"""

import curses
import json
import os
import glob

PAIR_HEADER      = 1   # Headers
PAIR_ACTIVE      = 2   # Badges (Hi-Res, EQ ON, etc.)
PAIR_PLAYING     = 3   # Current playing track
PAIR_MUTED       = 4   # Inactive / secondary text
PAIR_CURSOR      = 5   # Selected line cursor
PAIR_TEXT        = 6   # Regular text
PAIR_BORDER      = 7   # Lines and separators
PAIR_TAB_ACTIVE  = 8   # Active tab
PAIR_PROGRESS    = 9   # Progress bar
PAIR_SEARCH      = 10  # Search bar
PAIR_MODAL       = 11  # Modal body text
PAIR_MODAL_TITLE = 12  # Modal title

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    try:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return (r, g, b)
    except Exception:
        return (200, 200, 200)

def rgb_to_256(r, g, b):
    if abs(r - g) < 8 and abs(g - b) < 8:
        avg = (r + g + b) // 3
        if avg < 8:
            return 16
        if avg > 248:
            return 231
        return 232 + round((avg - 8) / 247 * 23)

    r_idx = min(5, max(0, round(r / 255 * 5)))
    g_idx = min(5, max(0, round(g / 255 * 5)))
    b_idx = min(5, max(0, round(b / 255 * 5)))
    return 16 + 36 * r_idx + 6 * g_idx + b_idx

DEFAULT_THEMES = {
    "Default": {
        "name": "Default",
        "description": "Clean minimalist cyan & green palette",
        "colors": {
            "header": "#50b0d0", "active": "#50c878", "playing": "#f0c040",
            "muted": "#708090", "cursor_fg": "#101010", "cursor_bg": "#50b0d0",
            "normal": "#dcdcdc", "border": "#404850", "tab_active_fg": "#101010",
            "tab_active_bg": "#50b0d0", "progress": "#50b0d0", "search": "#f0c040",
            "modal_fg": "#e0e0e0", "modal_bg": "#252b35", "modal_title": "#50b0d0"
        }
    },
    "Catppuccin Mocha": {
        "name": "Catppuccin Mocha",
        "description": "Soothing pastel tones",
        "colors": {
            "header": "#cba6f7", "active": "#a6e3a1", "playing": "#f9e2af",
            "muted": "#6c7086", "cursor_fg": "#1e1e2e", "cursor_bg": "#89b4fa",
            "normal": "#cdd6f4", "border": "#45475a", "tab_active_fg": "#1e1e2e",
            "tab_active_bg": "#cba6f7", "progress": "#89b4fa", "search": "#f9e2af",
            "modal_fg": "#cdd6f4", "modal_bg": "#313244", "modal_title": "#cba6f7"
        }
    },
    "Gruvbox Dark": {
        "name": "Gruvbox Dark",
        "description": "Warm retro groove palette",
        "colors": {
            "header": "#d3869b", "active": "#b8bb26", "playing": "#fabd2f",
            "muted": "#7c6f64", "cursor_fg": "#282828", "cursor_bg": "#83a598",
            "normal": "#ebdbb2", "border": "#504945", "tab_active_fg": "#282828",
            "tab_active_bg": "#83a598", "progress": "#83a598", "search": "#fabd2f",
            "modal_fg": "#ebdbb2", "modal_bg": "#3c3836", "modal_title": "#d3869b"
        }
    },
    "Nord": {
        "name": "Nord",
        "description": "Arctic blue clean palette",
        "colors": {
            "header": "#88c0d0", "active": "#a3be8c", "playing": "#ebcb8b",
            "muted": "#4c566a", "cursor_fg": "#2e3440", "cursor_bg": "#88c0d0",
            "normal": "#d8dee9", "border": "#434c5e", "tab_active_fg": "#2e3440",
            "tab_active_bg": "#81a1c1", "progress": "#88c0d0", "search": "#ebcb8b",
            "modal_fg": "#eceff4", "modal_bg": "#3b4252", "modal_title": "#88c0d0"
        }
    },
    "Dracula": {
        "name": "Dracula",
        "description": "High contrast dark palette",
        "colors": {
            "header": "#bd93f9", "active": "#50fa7b", "playing": "#f1fa8c",
            "muted": "#6272a4", "cursor_fg": "#282a36", "cursor_bg": "#bd93f9",
            "normal": "#f8f8f2", "border": "#44475a", "tab_active_fg": "#282a36",
            "tab_active_bg": "#ff79c6", "progress": "#8be9fd", "search": "#f1fa8c",
            "modal_fg": "#f8f8f2", "modal_bg": "#44475a", "modal_title": "#bd93f9"
        }
    },
    "Tokyo Night": {
        "name": "Tokyo Night",
        "description": "Deep midnight blue neon palette",
        "colors": {
            "header": "#7aa2f7", "active": "#9ece6a", "playing": "#e0af68",
            "muted": "#565f89", "cursor_fg": "#1a1b26", "cursor_bg": "#7aa2f7",
            "normal": "#a9b1d6", "border": "#3b4261", "tab_active_fg": "#1a1b26",
            "tab_active_bg": "#bb9af7", "progress": "#7dcfff", "search": "#e0af68",
            "modal_fg": "#c0caf5", "modal_bg": "#24283b", "modal_title": "#7aa2f7"
        }
    },
    "Rosé Pine": {
        "name": "Rosé Pine",
        "description": "Natural pine and rose pastel palette",
        "colors": {
            "header": "#ebbcba", "active": "#9ccfd8", "playing": "#f6c177",
            "muted": "#6e6a86", "cursor_fg": "#191724", "cursor_bg": "#c4a7e7",
            "normal": "#e0def4", "border": "#26233a", "tab_active_fg": "#191724",
            "tab_active_bg": "#ebbcba", "progress": "#9ccfd8", "search": "#f6c177",
            "modal_fg": "#e0def4", "modal_bg": "#21202e", "modal_title": "#ebbcba"
        }
    }
}

class ThemeEngine:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.builtin_dir = os.path.join(self.base_dir, "themes")
        # Hem ~/.config/pnut hem ~/.config/flac_player desteklenir
        self.user_dir = os.path.expanduser("~/.config/pnut/themes")
        self.legacy_user_dir = os.path.expanduser("~/.config/flac_player/themes")
        self.config_path = os.path.expanduser("~/.config/pnut/config.json")

        self.themes = dict(DEFAULT_THEMES)
        self.theme_names = []
        self.active_index = 0
        self.active_theme = None

        self._discover_themes()
        self._load_saved_preference()

    def _discover_themes(self):
        for d in [self.builtin_dir, self.legacy_user_dir, self.user_dir]:
            if os.path.isdir(d):
                for fpath in sorted(glob.glob(os.path.join(d, "*.json"))):
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        name = data.get("name")
                        if name and "colors" in data:
                            self.themes[name] = data
                    except Exception:
                        pass

        names = [n for n in self.themes if n != "Default"]
        self.theme_names = ["Default"] + sorted(names)

    def _load_saved_preference(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                saved = cfg.get("theme")
                if saved and saved in self.theme_names:
                    self.active_index = self.theme_names.index(saved)
        except Exception:
            pass
        self.active_theme = self.themes.get(self.theme_names[self.active_index], DEFAULT_THEMES["Default"])

    def _save_preference(self):
        try:
            cfg = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["theme"] = self.active_theme.get("name", "Default")
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def set_theme_by_name(self, name):
        if name in self.theme_names:
            self.active_index = self.theme_names.index(name)
            self.active_theme = self.themes[name]
            self._save_preference()
            return True
        return False

    def next_theme(self):
        self.active_index = (self.active_index + 1) % len(self.theme_names)
        self.active_theme = self.themes[self.theme_names[self.active_index]]
        self._save_preference()
        return self.active_theme

    def prev_theme(self):
        self.active_index = (self.active_index - 1 + len(self.theme_names)) % len(self.theme_names)
        self.active_theme = self.themes[self.theme_names[self.active_index]]
        self._save_preference()
        return self.active_theme

    def get_active_name(self):
        return self.active_theme.get("name", "Default")

    def apply_theme(self, stdscr):
        colors = self.active_theme.get("colors", DEFAULT_THEMES["Default"]["colors"])

        def c256(key, fallback_hex="#ffffff"):
            h = colors.get(key, fallback_hex)
            r, g, b = hex_to_rgb(h)
            return rgb_to_256(r, g, b)

        bg_default = -1

        curses.init_pair(PAIR_HEADER, c256("header", "#50b0d0"), bg_default)
        curses.init_pair(PAIR_ACTIVE, c256("active", "#50c878"), bg_default)
        curses.init_pair(PAIR_PLAYING, c256("playing", "#f0c040"), bg_default)
        curses.init_pair(PAIR_MUTED, c256("muted", "#708090"), bg_default)
        curses.init_pair(PAIR_CURSOR, c256("cursor_fg", "#101010"), c256("cursor_bg", "#50b0d0"))
        curses.init_pair(PAIR_TEXT, c256("normal", "#dcdcdc"), bg_default)
        curses.init_pair(PAIR_BORDER, c256("border", "#404850"), bg_default)
        curses.init_pair(PAIR_TAB_ACTIVE, c256("tab_active_fg", "#101010"), c256("tab_active_bg", "#50b0d0"))
        curses.init_pair(PAIR_PROGRESS, c256("progress", "#50b0d0"), bg_default)
        curses.init_pair(PAIR_SEARCH, c256("search", "#f0c040"), bg_default)
        curses.init_pair(PAIR_MODAL, c256("modal_fg", "#e0e0e0"), c256("modal_bg", "#252b35"))
        curses.init_pair(PAIR_MODAL_TITLE, c256("modal_title", "#50b0d0"), c256("modal_bg", "#252b35"))
