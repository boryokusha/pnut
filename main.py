#!/usr/bin/env python3
"""
pnut — Minimalist Audiophile Terminal Music Player
Optimized for CachyOS & PipeWire. Features Hi-Res Bit-Perfect Playback,
Parametric AutoEQ, Live Spectrum Visualizer (CAVA), and Synced Lyrics.
"""

import curses
import os
import sys
import time

from audio_engine import MPVAudioEngine
from eq_manager import EQManager
from playlist import LibraryManager, Track
from theme_engine import (
    ThemeEngine,
    PAIR_HEADER, PAIR_ACTIVE, PAIR_PLAYING, PAIR_MUTED,
    PAIR_CURSOR, PAIR_TEXT, PAIR_BORDER, PAIR_TAB_ACTIVE,
    PAIR_PROGRESS, PAIR_SEARCH, PAIR_MODAL, PAIR_MODAL_TITLE
)
from cover_art import CoverArtManager
from visualizer import AudioVisualizer, render_vertical_cava_column
from lyrics_manager import LyricsManager

def safe_addstr(win, y, x, text, attr=0):
    try:
        max_y, max_x = win.getmaxyx()
        if 0 <= y < max_y and 0 <= x < max_x:
            avail = max_x - x
            if y == max_y - 1 and avail > 0:
                avail -= 1
            if avail > 0:
                win.addstr(y, x, str(text)[:avail], attr)
    except curses.error:
        pass

def format_time(seconds):
    if seconds <= 0:
        return "00:00"
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m >= 60:
        h = m // 60
        m = m % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def render_progress_bar(width, ratio):
    if width <= 4:
        return ""
    ratio = max(0.0, min(1.0, ratio))
    filled_len = int(round((width - 1) * ratio))
    empty_len = (width - 1) - filled_len
    return "━" * filled_len + "●" + "─" * empty_len

# 2-line minimalist PNUT block logo
LOGO_L1 = "█▀█ █▄░█ █░█ ▀█▀"
LOGO_L2 = "█▀▀ █░▀█ █▄█ ░█░"

class PnutApp:
    def __init__(self, stdscr, music_dir=None):
        self.stdscr = stdscr
        self.engine = MPVAudioEngine()
        self.eq = EQManager()
        self.library = LibraryManager(music_dir)
        self.theme_engine = ThemeEngine()
        self.cover_mgr = CoverArtManager()
        self.lyrics_mgr = LyricsManager()
        self.visualizer = AudioVisualizer(num_bars=24)
        self.visualizer.start()

        # View state
        self.main_view = "library"          # "library" or "now_playing"
        self.np_submode = "spectrum"        # "spectrum" or "lyrics"
        self.selected_idx = 0
        self.scroll_offset = 0
        self.is_searching = False

        # Settings Modal
        self.show_settings = False
        self.settings_menu = [
            "📁 Change Music Directory",
            "🎨 Theme Selection",
            "🎧 IEM EQ Profiles",
            "⚡ Parametric EQ Status",
            "🌙 Sleep Timer",
            "⌨️ Keyboard Shortcuts"
        ]
        self.settings_idx = 0
        self.settings_subview = None
        self.subview_idx = 0

        # Custom path input state
        self.custom_path_input = ""
        self.is_typing_path = False

        # Sleep Timer
        self.sleep_timer_minutes = 0
        self.sleep_timer_end = 0

        self.status_msg = ""
        self.status_msg_time = 0

        self.cached_cover_track = None
        self.cached_cover_lines = []

        # Track transition tracker
        self.last_track_path = None
        self.track_finished_debounce = 0

        initial_lavfi = self.eq.build_lavfi_string()
        self.engine.apply_lavfi(initial_lavfi)

        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)
        curses.use_default_colors()
        self.theme_engine.apply_theme(self.stdscr)

    def set_status(self, msg):
        self.status_msg = msg
        self.status_msg_time = time.time()

    def play_track(self, track):
        if not track:
            return
        self.library.set_current_track(track)
        self.engine.load_file(track.path)
        lavfi = self.eq.build_lavfi_string()
        self.engine.apply_lavfi(lavfi)
        self.cached_cover_track = None
        self.last_track_path = track.path
        self.lyrics_mgr.load_lyrics_for_track(track)
        self.set_status(f"Playing: {track.artist} - {track.title}")

    def run(self):
        last_refresh = 0
        playback_state = {}

        try:
            while True:
                now = time.time()

                if self.sleep_timer_end > 0 and now >= self.sleep_timer_end:
                    self.engine.pause()
                    self.sleep_timer_end = 0
                    self.sleep_timer_minutes = 0
                    self.set_status("Sleep timer reached: Playback paused")

                if now - last_refresh >= 0.045:
                    playback_state = self.engine.get_status()
                    self.check_auto_track_transition(playback_state, now)
                    self.draw(playback_state)
                    last_refresh = now

                try:
                    ch = self.stdscr.getch()
                except Exception:
                    ch = -1

                if ch != -1:
                    if self.handle_input(ch):
                        break

                time.sleep(0.015)
        finally:
            self.visualizer.stop()
            self.engine.quit()

    def check_auto_track_transition(self, state, now):
        curr_track = self.library.get_current_track()
        if not curr_track or state.get("is_paused"):
            return

        pos = state.get("time_pos", 0)
        dur = state.get("duration", 0)
        eof = state.get("eof_reached", False)

        is_finished = eof or (dur > 2.0 and pos >= dur - 0.45)
        if is_finished and (now - self.track_finished_debounce > 1.2):
            self.track_finished_debounce = now
            next_t = self.library.get_next_track(is_auto_end=True)
            if next_t:
                self.play_track(next_t)

    def handle_input(self, ch):
        items = self.library.get_view_items()

        # 1. Search Mode
        if self.is_searching:
            if ch == 27:
                self.is_searching = False
                self.library.search_query = ""
                self.selected_idx = 0
            elif ch in (10, 13, curses.KEY_ENTER):
                self.is_searching = False
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.library.search_query:
                    self.library.search_query = self.library.search_query[:-1]
                    self.selected_idx = 0
            elif 32 <= ch <= 126:
                self.library.search_query += chr(ch)
                self.selected_idx = 0
            return False

        # 2. Settings Modal
        if self.show_settings:
            return self.handle_settings_input(ch)

        # 3. Global Shortcuts
        if ch in (ord('q'), ord('Q')):
            return True

        elif ch in (ord('s'), ord('S')):
            self.show_settings = True
            self.settings_subview = None
            self.settings_idx = 0
            return False

        elif ch in (ord('o'), ord('O')):
            # Quick open music directory selector
            self.show_settings = True
            self.settings_subview = "music_dir"
            self.subview_idx = 0
            self.is_typing_path = False
            return False

        elif ch in (ord('v'), ord('V')):
            self.main_view = "now_playing" if self.main_view == "library" else "library"
            mode_name = "Studio View" if self.main_view == "now_playing" else "Library View"
            self.set_status(f"View: {mode_name}")
            return False

        elif ch in (ord('l'), ord('L')) and self.main_view == "now_playing":
            self.np_submode = "lyrics" if self.np_submode == "spectrum" else "spectrum"
            self.set_status(f"Panel: {'Lyrics' if self.np_submode == 'lyrics' else 'Spectrum'}")
            return False

        elif ch == ord('/'):
            self.is_searching = True
            self.library.search_query = ""

        # Flow Controls: Shuffle & Repeat
        elif ch in (ord('z'), ord('Z')):
            shuf = self.library.toggle_shuffle()
            self.set_status(f"Shuffle: {'ON (🔀)' if shuf else 'OFF'}")

        elif ch in (ord('r'), ord('R')):
            rep = self.library.cycle_repeat()
            rep_label = "ALL (🔁)" if rep == "all" else ("SINGLE (🔂)" if rep == "single" else "OFF")
            self.set_status(f"Repeat: {rep_label}")

        # Queue & Favorites
        elif ch in (ord('a'), ord('A')):
            if items and 0 <= self.selected_idx < len(items):
                item = items[self.selected_idx]
                if isinstance(item, Track):
                    q_len = self.library.add_to_queue(item)
                    self.set_status(f"Added to Queue: {item.title} (#{q_len})")
                else:
                    self.set_status("Only individual tracks can be queued")

        elif ch in (ord('f'), ord('F')):
            target_track = None
            if items and 0 <= self.selected_idx < len(items) and isinstance(items[self.selected_idx], Track):
                target_track = items[self.selected_idx]
            else:
                target_track = self.library.get_current_track()

            if target_track:
                is_fav = self.library.toggle_favorite(target_track)
                st = "Added to Favorites (★)" if is_fav else "Removed from Favorites"
                self.set_status(f"{st}: {target_track.title}")

        elif ch in (ord('d'), ord('D')) and self.library.current_view == LibraryManager.VIEW_QUEUE:
            removed = self.library.remove_from_queue(self.selected_idx)
            if removed:
                self.set_status(f"Removed from queue: {removed.title}")
                self.selected_idx = max(0, min(self.selected_idx, len(self.library.queue) - 1))

        # Library Tabs
        elif ch == ord('1'):
            self.main_view = "library"
            self.library.current_view = LibraryManager.VIEW_TRACKS
            self.selected_idx = 0
            self.scroll_offset = 0

        elif ch == ord('2'):
            self.main_view = "library"
            self.library.current_view = LibraryManager.VIEW_ARTISTS
            self.selected_idx = 0
            self.scroll_offset = 0

        elif ch == ord('3'):
            self.main_view = "library"
            self.library.current_view = LibraryManager.VIEW_ALBUMS
            self.selected_idx = 0
            self.scroll_offset = 0

        elif ch == ord('4'):
            self.main_view = "library"
            self.library.current_view = LibraryManager.VIEW_FAVORITES
            self.selected_idx = 0
            self.scroll_offset = 0
            self.set_status("View: Favorites (★)")

        elif ch == ord('5'):
            self.main_view = "library"
            self.library.current_view = LibraryManager.VIEW_QUEUE
            self.selected_idx = 0
            self.scroll_offset = 0
            self.set_status(f"View: Queue ({len(self.library.queue)} tracks)")

        elif ch in (ord('c'), ord('C')):
            self.library.clear_filters()
            self.selected_idx = 0
            self.scroll_offset = 0
            self.set_status("Filter cleared")

        # Navigation
        elif ch in (curses.KEY_DOWN, ord('j')):
            if items and self.selected_idx < len(items) - 1:
                self.selected_idx += 1
        elif ch in (curses.KEY_UP, ord('k')):
            if items and self.selected_idx > 0:
                self.selected_idx -= 1
        elif ch == curses.KEY_NPAGE:
            self.selected_idx = min(len(items) - 1, self.selected_idx + 10)
        elif ch == curses.KEY_PPAGE:
            self.selected_idx = max(0, self.selected_idx - 10)

        # Selection / Playback
        elif ch in (10, 13, curses.KEY_ENTER):
            if items and 0 <= self.selected_idx < len(items):
                item = items[self.selected_idx]
                if self.library.current_view == LibraryManager.VIEW_ARTISTS:
                    self.library.filter_by_artist(item["name"])
                    self.selected_idx = 0
                    self.scroll_offset = 0
                elif self.library.current_view == LibraryManager.VIEW_ALBUMS:
                    self.library.filter_by_album(item["key"])
                    self.selected_idx = 0
                    self.scroll_offset = 0
                elif self.library.current_view == LibraryManager.VIEW_QUEUE:
                    popped = self.library.remove_from_queue(self.selected_idx)
                    self.play_track(popped)
                    self.selected_idx = max(0, min(self.selected_idx, len(self.library.queue) - 1))
                else:
                    self.play_track(item)

        elif ch == ord(' '):
            self.engine.toggle_pause()

        elif ch == curses.KEY_RIGHT or (ch == ord('l') and self.main_view != "now_playing"):
            self.engine.seek(5)
        elif ch in (curses.KEY_LEFT, ord('h')):
            self.engine.seek(-5)

        elif ch == ord('n'):
            nxt = self.library.get_next_track(is_auto_end=False)
            if nxt:
                self.play_track(nxt)
        elif ch == ord('b'):
            prv = self.library.get_prev_track()
            if prv:
                self.play_track(prv)

        elif ch in (ord('+'), ord('=')):
            self.engine.change_volume(5)
            self.set_status(f"Volume: {self.engine.volume}%")
        elif ch in (ord('-'), ord('_')):
            self.engine.change_volume(-5)
            self.set_status(f"Volume: {self.engine.volume}%")

        return False

    def handle_settings_input(self, ch):
        if self.is_typing_path:
            if ch == 27:  # ESC
                self.is_typing_path = False
                self.custom_path_input = ""
            elif ch in (10, 13, curses.KEY_ENTER):
                if self.custom_path_input.strip():
                    ok, res = self.library.set_music_directory(self.custom_path_input.strip())
                    if ok:
                        self.set_status(f"Loaded {len(self.library.all_tracks)} tracks from {os.path.basename(res)}")
                        self.selected_idx = 0
                        self.scroll_offset = 0
                        self.show_settings = False
                    else:
                        self.set_status(f"Error: {res}")
                self.is_typing_path = False
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.custom_path_input:
                    self.custom_path_input = self.custom_path_input[:-1]
            elif 32 <= ch <= 126:
                self.custom_path_input += chr(ch)
            return False

        if ch in (27, ord('q'), ord('Q')):
            if self.settings_subview is not None:
                self.settings_subview = None
            else:
                self.show_settings = False
            return False

        if self.settings_subview is None:
            if ch in (curses.KEY_DOWN, ord('j')):
                self.settings_idx = (self.settings_idx + 1) % len(self.settings_menu)
            elif ch in (curses.KEY_UP, ord('k')):
                self.settings_idx = (self.settings_idx - 1 + len(self.settings_menu)) % len(self.settings_menu)
            elif ch in (10, 13, curses.KEY_ENTER, ord(' ')):
                if self.settings_idx == 0:
                    self.settings_subview = "music_dir"
                    self.subview_idx = 0
                elif self.settings_idx == 1:
                    self.settings_subview = "themes"
                    self.subview_idx = self.theme_engine.active_index
                elif self.settings_idx == 2:
                    self.settings_subview = "eq_profiles"
                    self.subview_idx = self.eq.active_index
                elif self.settings_idx == 3:
                    enabled = self.eq.toggle()
                    lavfi = self.eq.build_lavfi_string()
                    self.engine.apply_lavfi(lavfi)
                    self.set_status(f"EQ: {'ENABLED' if enabled else 'DISABLED (Bypass)'}")
                elif self.settings_idx == 4:
                    self.settings_subview = "sleep_timer"
                elif self.settings_idx == 5:
                    self.settings_subview = "help"
            return False

        if self.settings_subview == "music_dir":
            home = os.path.expanduser("~")
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dir_options = [
                ("Project music folder", os.path.join(base_dir, "music")),
                ("Standard Music folder", os.path.join(home, "Music")),
                ("Turkish Müzik folder", os.path.join(home, "Müzik")),
                ("Downloads folder", os.path.join(home, "Downloads")),
                ("Turkish İndirilenler", os.path.join(home, "İndirilenler")),
                ("Custom Path...", "custom")
            ]
            if ch in (curses.KEY_DOWN, ord('j')):
                self.subview_idx = (self.subview_idx + 1) % len(dir_options)
            elif ch in (curses.KEY_UP, ord('k')):
                self.subview_idx = (self.subview_idx - 1 + len(dir_options)) % len(dir_options)
            elif ch in (10, 13, curses.KEY_ENTER, ord(' ')):
                _, path_val = dir_options[self.subview_idx]
                if path_val == "custom":
                    self.is_typing_path = True
                    self.custom_path_input = ""
                else:
                    ok, res = self.library.set_music_directory(path_val)
                    if ok:
                        self.set_status(f"Loaded {len(self.library.all_tracks)} tracks from {os.path.basename(res)}")
                        self.selected_idx = 0
                        self.scroll_offset = 0
                        self.show_settings = False
                    else:
                        self.set_status(f"Error: {res}")
            return False

        if self.settings_subview == "sleep_timer":
            timer_options = [0, 15, 30, 45, 60, 90]
            if ch in (curses.KEY_DOWN, ord('j')):
                self.subview_idx = (self.subview_idx + 1) % len(timer_options)
            elif ch in (curses.KEY_UP, ord('k')):
                self.subview_idx = (self.subview_idx - 1 + len(timer_options)) % len(timer_options)
            elif ch in (10, 13, curses.KEY_ENTER, ord(' ')):
                chosen_mins = timer_options[self.subview_idx]
                self.sleep_timer_minutes = chosen_mins
                if chosen_mins > 0:
                    self.sleep_timer_end = time.time() + (chosen_mins * 60)
                    self.set_status(f"Sleep timer set: {chosen_mins} minutes (🌙)")
                else:
                    self.sleep_timer_end = 0
                    self.set_status("Sleep timer disabled")
                self.settings_subview = None
            return False

        if self.settings_subview == "themes":
            t_names = self.theme_engine.theme_names
            if ch in (curses.KEY_DOWN, ord('j')):
                self.subview_idx = (self.subview_idx + 1) % len(t_names)
            elif ch in (curses.KEY_UP, ord('k')):
                self.subview_idx = (self.subview_idx - 1 + len(t_names)) % len(t_names)
            elif ch in (10, 13, curses.KEY_ENTER, ord(' ')):
                chosen = t_names[self.subview_idx]
                self.theme_engine.set_theme_by_name(chosen)
                self.theme_engine.apply_theme(self.stdscr)
                self.set_status(f"Theme: {chosen}")
            return False

        if self.settings_subview == "eq_profiles":
            presets = self.eq.presets
            if ch in (curses.KEY_DOWN, ord('j')):
                if presets:
                    self.subview_idx = (self.subview_idx + 1) % len(presets)
            elif ch in (curses.KEY_UP, ord('k')):
                if presets:
                    self.subview_idx = (self.subview_idx - 1 + len(presets)) % len(presets)
            elif ch in (10, 13, curses.KEY_ENTER, ord(' ')):
                self.eq.active_index = self.subview_idx
                lavfi = self.eq.build_lavfi_string()
                self.engine.apply_lavfi(lavfi)
                self.set_status(f"IEM Profile: {presets[self.subview_idx]['name']}")
            elif ch in (ord('d'), ord('D')):
                curr = presets[self.subview_idx] if presets else None
                if curr and curr.get("is_user_custom"):
                    pid = curr.get("id")
                    if self.eq.delete_user_profile(pid):
                        self.set_status(f"Deleted: {curr['name']}")
                        self.subview_idx = max(0, min(self.subview_idx, len(self.eq.presets) - 1))
                        lavfi = self.eq.build_lavfi_string()
                        self.engine.apply_lavfi(lavfi)
            return False

        if self.settings_subview == "help":
            if ch in (27, ord('q'), ord('Q'), 10, 13):
                self.settings_subview = None
            return False

        return False

    def get_cover_lines(self, track, width, height):
        if not track:
            return self.cover_mgr.render_cover_ascii(None, width, height)
        if self.cached_cover_track != track.path:
            img_path = self.cover_mgr.get_cover_image_path(track.path)
            lines = self.cover_mgr.render_cover_chafa(img_path, width, height)
            if not lines:
                lines = self.cover_mgr.render_cover_ascii(img_path, width, height)
            self.cached_cover_track = track.path
            self.cached_cover_lines = lines
        return self.cached_cover_lines

    def draw(self, state):
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()

        if max_y < 12 or max_x < 50:
            safe_addstr(self.stdscr, 0, 0, "Please enlarge terminal window")
            self.stdscr.refresh()
            return

        self.draw_top_header(state, max_x)

        if self.main_view == "now_playing":
            self.draw_now_playing_split(state, max_y, max_x)
        else:
            self.draw_library_view(state, max_y, max_x)

        if self.show_settings:
            self.render_settings_modal(max_y, max_x)

        self.stdscr.refresh()

    def draw_top_header(self, state, max_x):
        safe_addstr(self.stdscr, 0, 2, LOGO_L1, curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
        safe_addstr(self.stdscr, 1, 2, LOGO_L2, curses.color_pair(PAIR_HEADER) | curses.A_BOLD)

        header_content_x = len(LOGO_L1) + 4
        avail_w = max_x - header_content_x - 2

        if avail_w > 18:
            safe_addstr(self.stdscr, 0, header_content_x - 2, "│", curses.color_pair(PAIR_BORDER))
            safe_addstr(self.stdscr, 1, header_content_x - 2, "│", curses.color_pair(PAIR_BORDER))

            current_track = self.library.get_current_track()
            title = state.get("title") or (current_track.title if current_track else "No Track Playing")
            artist = state.get("artist") or (current_track.artist if current_track else "")
            album = state.get("album") or (current_track.album if current_track else "")
            sr = state.get("samplerate")
            fmt = state.get("format") or ""

            fmt_badge = "Lossless"
            if sr:
                sr_khz = sr / 1000.0
                fmt_badge = f"{sr_khz:.1f}kHz"
                if "s24" in fmt.lower() or "24" in fmt.lower():
                    fmt_badge = f"24b/{sr_khz:.1f}k"
                elif "s32" in fmt.lower():
                    fmt_badge = f"32b/{sr_khz:.1f}k"

            active_preset = self.eq.get_active_preset()
            eq_name = active_preset["name"][:10] if (self.eq.is_enabled and active_preset) else "Bypass"

            flow_badges = []
            if self.library.shuffle:
                flow_badges.append("🔀")
            if self.library.repeat_mode == "all":
                flow_badges.append("🔁")
            elif self.library.repeat_mode == "single":
                flow_badges.append("🔂")
            if self.library.is_favorite(current_track):
                flow_badges.append("★")
            if self.sleep_timer_end > 0:
                rem_mins = int((self.sleep_timer_end - time.time()) // 60) + 1
                flow_badges.append(f"🌙{rem_mins}m")

            flow_str = " ".join(flow_badges)
            if flow_str:
                badges = f"[{fmt_badge}] [{eq_name}] [{flow_str}]"
            else:
                badges = f"[{fmt_badge}] [{eq_name}]"

            pb_icon = "❚❚" if state.get("is_paused") else "▶"
            fav_star = "★ " if self.library.is_favorite(current_track) else ""
            track_str = f"{pb_icon} {fav_star}{title}"
            if artist:
                track_str += f" — {artist}"
            if album and avail_w > 70:
                track_str += f" ({album})"

            space_for_track = avail_w - len(badges) - 2
            if space_for_track > 12:
                safe_addstr(self.stdscr, 0, header_content_x, track_str[:space_for_track], curses.color_pair(PAIR_PLAYING) | curses.A_BOLD)
                safe_addstr(self.stdscr, 0, header_content_x + space_for_track + 1, badges, curses.color_pair(PAIR_ACTIVE))
            else:
                safe_addstr(self.stdscr, 0, header_content_x, track_str[:avail_w], curses.color_pair(PAIR_PLAYING) | curses.A_BOLD)

            pos_str = format_time(state.get("time_pos", 0))
            dur_str = format_time(state.get("duration", 0))
            dur_val = state.get("duration", 0)
            pos_val = state.get("time_pos", 0)
            ratio = (pos_val / dur_val) if dur_val > 0 else 0.0

            q_info = f"[Q:{len(self.library.queue)}] " if self.library.queue else ""
            vol_str = f"[Vol: {state.get('volume', 100)}%]"
            time_prefix = f"{pos_str} "
            time_suffix = f" {dur_str}  {q_info}{vol_str}"

            bar_width = max(8, avail_w - len(time_prefix) - len(time_suffix))
            p_bar = render_progress_bar(bar_width, ratio)

            safe_addstr(self.stdscr, 1, header_content_x, f"{time_prefix}{p_bar}{time_suffix}"[:avail_w], curses.color_pair(PAIR_PROGRESS))

        safe_addstr(self.stdscr, 2, 0, "─" * (max_x - 1), curses.color_pair(PAIR_BORDER))

    def draw_now_playing_split(self, state, max_y, max_x):
        current_track = self.library.get_current_track()
        content_top = 3
        content_bottom = max_y - 2
        content_h = max(6, content_bottom - content_top)

        split_x = max(30, min(int(max_x * 0.42), 46))

        cover_w = min(28, split_x - 6)
        cover_h = min(14, content_h - 2)
        cover_lines = self.get_cover_lines(current_track, cover_w, cover_h)

        c_start_y = content_top + 1
        for idx, line in enumerate(cover_lines[:cover_h]):
            safe_addstr(self.stdscr, c_start_y + idx, 3, line[:cover_w], curses.color_pair(PAIR_TEXT))

        for y in range(content_top, content_bottom):
            safe_addstr(self.stdscr, y, split_x, "│", curses.color_pair(PAIR_BORDER))

        right_w = max_x - split_x - 3
        right_start_x = split_x + 3

        if right_w > 12:
            if self.np_submode == "lyrics":
                lyrics_title = "◈ SYNCED LYRICS ◈  ([l] Spectrum)"
                safe_addstr(self.stdscr, content_top, right_start_x, lyrics_title[:right_w], curses.color_pair(PAIR_BORDER))

                lines_area_top = content_top + 2
                avail_lines = max(3, content_bottom - lines_area_top - 1)

                visible, local_active = self.lyrics_mgr.get_window(state.get("time_pos", 0), avail_lines)
                if visible:
                    for l_idx, line_obj in enumerate(visible):
                        row_y = lines_area_top + l_idx
                        is_active = (l_idx == local_active)
                        prefix = "▶ " if is_active else "  "
                        color = (curses.color_pair(PAIR_PLAYING) | curses.A_BOLD) if is_active else curses.color_pair(PAIR_MUTED)
                        safe_addstr(self.stdscr, row_y, right_start_x + 1, f"{prefix}{line_obj.text}"[:right_w - 2], color)
                else:
                    st_text = self.lyrics_mgr.status_text or "No lyrics available"
                    safe_addstr(self.stdscr, lines_area_top + 2, right_start_x + 2, f"({st_text})", curses.color_pair(PAIR_MUTED))
            else:
                spec_title = "◈ SPECTRUM VISUALIZER (CAVA) ◈  ([l] Lyrics)"
                safe_addstr(self.stdscr, content_top, right_start_x, spec_title[:right_w], curses.color_pair(PAIR_BORDER))

                bars_area_top = content_top + 2
                bars_area_bottom = content_bottom - 2
                bars_h = max(4, bars_area_bottom - bars_area_top)

                num_bars_to_draw = min(32, max(8, right_w // 2))
                raw_bars = self.visualizer.get_bars()

                if len(raw_bars) != num_bars_to_draw:
                    import numpy as np
                    interp_bars = np.interp(
                        np.linspace(0, len(raw_bars) - 1, num_bars_to_draw),
                        np.arange(len(raw_bars)),
                        raw_bars
                    )
                else:
                    interp_bars = raw_bars

                for b_idx, val in enumerate(interp_bars):
                    col_chars = render_vertical_cava_column(bars_h, val)
                    col_x = right_start_x + (b_idx * 2)
                    if col_x >= max_x - 2:
                        break

                    for r_idx, char in enumerate(col_chars):
                        row_y = bars_area_top + r_idx
                        if r_idx < bars_h // 3:
                            color = PAIR_PLAYING
                        elif r_idx < 2 * (bars_h // 3):
                            color = PAIR_PROGRESS
                        else:
                            color = PAIR_ACTIVE
                        safe_addstr(self.stdscr, row_y, col_x, char, curses.color_pair(color))

                labels = "  BASS          MID / VOCAL         TREBLE  "
                safe_addstr(self.stdscr, bars_area_bottom + 1, right_start_x + 1, labels[:right_w], curses.color_pair(PAIR_BORDER))

        self.render_bottom_bar(max_y, max_x)

    def draw_library_view(self, state, max_y, max_x):
        tab_y = 3
        q_count = len(self.library.queue)
        q_tab = f" [5] Queue ({q_count}) " if q_count else " [5] Queue "
        fav_count = len(self.library.favorites)

        tabs = [
            (LibraryManager.VIEW_TRACKS, " [1] Tracks "),
            (LibraryManager.VIEW_ARTISTS, " [2] Artists "),
            (LibraryManager.VIEW_ALBUMS, " [3] Albums "),
            (LibraryManager.VIEW_FAVORITES, f" [4] Favs ({fav_count}) "),
            (LibraryManager.VIEW_QUEUE, q_tab)
        ]
        curr_x = 2
        for view_id, label in tabs:
            if self.library.current_view == view_id:
                safe_addstr(self.stdscr, tab_y, curr_x, label, curses.color_pair(PAIR_TAB_ACTIVE) | curses.A_BOLD)
            else:
                safe_addstr(self.stdscr, tab_y, curr_x, label, curses.color_pair(PAIR_MUTED))
            curr_x += len(label) + 1

        # Current folder indicator
        folder_label = f"📁 {os.path.basename(self.library.root_dir) or '/'}"
        if curr_x + len(folder_label) < max_x - 4:
            safe_addstr(self.stdscr, tab_y, curr_x, f" [{folder_label}]", curses.color_pair(PAIR_MUTED))
            curr_x += len(folder_label) + 4

        if self.library.filter_artist:
            f_str = f" [Artist: {self.library.filter_artist}]"
            if curr_x + len(f_str) < max_x - 4:
                safe_addstr(self.stdscr, tab_y, curr_x, f_str, curses.color_pair(PAIR_PLAYING))
        elif self.library.filter_album:
            alb_n, _ = self.library.filter_album
            f_str = f" [Album: {alb_n}]"
            if curr_x + len(f_str) < max_x - 4:
                safe_addstr(self.stdscr, tab_y, curr_x, f_str, curses.color_pair(PAIR_PLAYING))

        list_top = 5
        list_bottom = max_y - 2
        list_height = max(1, list_bottom - list_top)

        items = self.library.get_view_items()
        current_track = self.library.get_current_track()

        if self.selected_idx < self.scroll_offset:
            self.scroll_offset = self.selected_idx
        elif self.selected_idx >= self.scroll_offset + list_height:
            self.scroll_offset = self.selected_idx - list_height + 1
        self.scroll_offset = max(0, min(self.scroll_offset, max(0, len(items) - list_height)))

        for i in range(list_height):
            idx = self.scroll_offset + i
            row_y = list_top + i
            if idx >= len(items):
                break

            item = items[idx]
            is_cursor = (idx == self.selected_idx)

            if isinstance(item, Track):
                is_playing = (current_track and item.path == current_track.path)
                is_fav = self.library.is_favorite(item)
                fav_badge = "★ " if is_fav else "  "
                prefix = "▶ " if is_playing else "  "
                num_str = f"{idx + 1:<3} "

                if max_x >= 80:
                    t_title = item.title[:28].ljust(29)
                    t_art = item.artist[:22].ljust(23)
                    t_alb = item.album[:max_x - 68]
                    row_str = f" {prefix}{fav_badge}{num_str}{t_title} {t_art} {t_alb}"
                else:
                    row_str = f" {prefix}{fav_badge}{num_str}{item.artist} - {item.title}"

                row_str = row_str[:max_x - 4].ljust(max_x - 4)

                if is_cursor:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                elif is_playing:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_PLAYING) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_TEXT))

            elif self.library.current_view == LibraryManager.VIEW_ARTISTS:
                art_name = item["name"]
                cnt_str = f"({item['count']} tracks)"
                row_str = f"   {art_name:<40} {cnt_str}"
                row_str = row_str[:max_x - 4].ljust(max_x - 4)
                if is_cursor:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_TEXT))

            elif self.library.current_view == LibraryManager.VIEW_ALBUMS:
                alb_name = item["name"][:30].ljust(31)
                alb_art = item["artist"][:20].ljust(21)
                cnt_str = f"({item['count']} tracks)"
                row_str = f"   {alb_name} {alb_art} {cnt_str}"
                row_str = row_str[:max_x - 4].ljust(max_x - 4)
                if is_cursor:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row_y, 2, row_str, curses.color_pair(PAIR_TEXT))

        self.render_bottom_bar(max_y, max_x)

    def render_bottom_bar(self, max_y, max_x):
        safe_addstr(self.stdscr, max_y - 2, 0, "─" * (max_x - 1), curses.color_pair(PAIR_BORDER))
        if time.time() - self.status_msg_time < 2.5 and self.status_msg:
            safe_addstr(self.stdscr, max_y - 1, 2, f"● {self.status_msg}"[:max_x - 4], curses.color_pair(PAIR_ACTIVE) | curses.A_BOLD)
        elif self.is_searching:
            safe_addstr(self.stdscr, max_y - 1, 2, f"Search: {self.library.search_query}_"[:max_x - 4], curses.color_pair(PAIR_SEARCH) | curses.A_BOLD)
        else:
            bar_text = " [o] Open Folder  [s] Settings  [v] View  [z] Shuf  [r] Rep  [a] Queue  [f] Fav  [q] Quit"
            safe_addstr(self.stdscr, max_y - 1, 2, bar_text[:max_x - 4], curses.color_pair(PAIR_MUTED))

    def render_settings_modal(self, max_y, max_x):
        modal_w = min(68, max_x - 4)
        modal_h = min(20, max_y - 4)
        start_x = (max_x - modal_w) // 2
        start_y = (max_y - modal_h) // 2

        for y in range(modal_h):
            safe_addstr(self.stdscr, start_y + y, start_x, " " * modal_w, curses.color_pair(PAIR_MODAL))

        if self.settings_subview is None:
            title = " ⚙ SETTINGS ⚙ "
            safe_addstr(self.stdscr, start_y + 1, start_x + (modal_w - len(title)) // 2, title, curses.color_pair(PAIR_MODAL_TITLE) | curses.A_BOLD)

            for idx, item in enumerate(self.settings_menu):
                row = start_y + 4 + idx
                is_cursor = (idx == self.settings_idx)
                line_str = f"  {item}"
                if idx == 0:
                    dir_name = os.path.basename(self.library.root_dir) or "/"
                    line_str += f"  ({dir_name})"
                elif idx == 1:
                    line_str += f"  ({self.theme_engine.get_active_name()})"
                elif idx == 2:
                    p = self.eq.get_active_preset()
                    line_str += f"  ({p['name'] if p else 'None'})"
                elif idx == 3:
                    st = "ON" if self.eq.is_enabled else "OFF"
                    line_str += f"  [{st}]"
                elif idx == 4:
                    st = f"{self.sleep_timer_minutes}m" if self.sleep_timer_minutes > 0 else "OFF"
                    line_str += f"  [{st}]"

                line_str = line_str[:modal_w - 6].ljust(modal_w - 6)
                if is_cursor:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_MODAL))

            footer = " [Enter] Select   [ESC/q] Close "
            safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))

        elif self.settings_subview == "music_dir":
            title = " 📁 SELECT MUSIC DIRECTORY 📁 "
            safe_addstr(self.stdscr, start_y + 1, start_x + (modal_w - len(title)) // 2, title, curses.color_pair(PAIR_MODAL_TITLE) | curses.A_BOLD)

            if self.is_typing_path:
                prompt = "Enter directory path (e.g. /mnt/music):"
                safe_addstr(self.stdscr, start_y + 4, start_x + 3, prompt, curses.color_pair(PAIR_MODAL))
                input_box = f"> {self.custom_path_input}_"
                safe_addstr(self.stdscr, start_y + 6, start_x + 3, input_box[:modal_w - 6], curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                footer = " [Enter] Confirm Path   [ESC] Cancel "
                safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))
            else:
                curr_hint = f"Current: {self.library.root_dir}"
                safe_addstr(self.stdscr, start_y + 3, start_x + 3, curr_hint[:modal_w - 6], curses.color_pair(PAIR_ACTIVE))

                home = os.path.expanduser("~")
                base_dir = os.path.dirname(os.path.abspath(__file__))
                options = [
                    ("📁 ./music (Project folder)", os.path.join(base_dir, "music")),
                    ("📁 ~/Music", os.path.join(home, "Music")),
                    ("📁 ~/Müzik (Turkish locale)", os.path.join(home, "Müzik")),
                    ("📁 ~/Downloads", os.path.join(home, "Downloads")),
                    ("📁 ~/İndirilenler", os.path.join(home, "İndirilenler")),
                    ("✏️ Custom Path...", "custom")
                ]

                for idx, (label, pval) in enumerate(options):
                    row = start_y + 5 + idx
                    is_cursor = (idx == self.subview_idx)
                    is_active = (os.path.abspath(pval) == os.path.abspath(self.library.root_dir)) if pval != "custom" else False
                    prefix = " [*] " if is_active else " [ ] "
                    line_str = f"{prefix}{label}".ljust(modal_w - 6)

                    if is_cursor:
                        safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                    elif is_active:
                        safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_ACTIVE) | curses.A_BOLD)
                    else:
                        safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_MODAL))

                footer = " [Enter] Select   [ESC] Back "
                safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))

        elif self.settings_subview == "sleep_timer":
            title = " 🌙 SLEEP TIMER 🌙 "
            safe_addstr(self.stdscr, start_y + 1, start_x + (modal_w - len(title)) // 2, title, curses.color_pair(PAIR_MODAL_TITLE) | curses.A_BOLD)

            options = [
                (0, "Disabled (Off)"),
                (15, "15 Minutes"),
                (30, "30 Minutes"),
                (45, "45 Minutes"),
                (60, "60 Minutes (1 Hour)"),
                (90, "90 Minutes")
            ]
            for idx, (mins, label) in enumerate(options):
                row = start_y + 4 + idx
                is_cursor = (idx == self.subview_idx)
                is_active = (mins == self.sleep_timer_minutes)
                prefix = " [*] " if is_active else " [ ] "
                line_str = f"{prefix}{label}".ljust(modal_w - 6)

                if is_cursor:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                elif is_active:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_ACTIVE) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_MODAL))

            footer = " [Enter] Set Timer   [ESC] Back "
            safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))

        elif self.settings_subview == "themes":
            title = " 🎨 THEME SELECTION 🎨 "
            safe_addstr(self.stdscr, start_y + 1, start_x + (modal_w - len(title)) // 2, title, curses.color_pair(PAIR_MODAL_TITLE) | curses.A_BOLD)

            t_names = self.theme_engine.theme_names
            max_show = min(modal_h - 6, len(t_names))
            for idx in range(max_show):
                tname = t_names[idx]
                row = start_y + 4 + idx
                is_cursor = (idx == self.subview_idx)
                is_active = (tname == self.theme_engine.get_active_name())
                prefix = " [*] " if is_active else " [ ] "
                line_str = f"{prefix}{tname}".ljust(modal_w - 6)

                if is_cursor:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                elif is_active:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_ACTIVE) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_MODAL))

            footer = " [Enter] Apply   [ESC] Back "
            safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))

        elif self.settings_subview == "eq_profiles":
            title = " 🎧 IEM EQ PROFILES 🎧 "
            safe_addstr(self.stdscr, start_y + 1, start_x + (modal_w - len(title)) // 2, title, curses.color_pair(PAIR_MODAL_TITLE) | curses.A_BOLD)

            presets = self.eq.presets
            max_show = min(modal_h - 6, len(presets))
            for idx in range(max_show):
                p = presets[idx]
                row = start_y + 4 + idx
                is_cursor = (idx == self.subview_idx)
                is_active = (idx == self.eq.active_index)
                prefix = " [*] " if is_active else " [ ] "
                custom = " (Custom)" if p.get("is_user_custom") else ""
                line_str = f"{prefix}{p['name']}{custom}"[:modal_w - 6].ljust(modal_w - 6)

                if is_cursor:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_CURSOR) | curses.A_BOLD)
                elif is_active:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_ACTIVE) | curses.A_BOLD)
                else:
                    safe_addstr(self.stdscr, row, start_x + 3, line_str, curses.color_pair(PAIR_MODAL))

            footer = " [Enter] Select   [d] Delete Custom   [ESC] Back "
            safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))

        elif self.settings_subview == "help":
            title = " ⌨️ KEYBOARD SHORTCUTS ⌨️ "
            safe_addstr(self.stdscr, start_y + 1, start_x + (modal_w - len(title)) // 2, title, curses.color_pair(PAIR_MODAL_TITLE) | curses.A_BOLD)

            shortcuts = [
                ("o", "Quick Open/Change Music Directory"),
                ("s", "Open Settings (Music Dir, Themes, IEM EQ)"),
                ("z", "Toggle Shuffle (🔀)"),
                ("r", "Cycle Repeat (Off -> All -> Single)"),
                ("a", "Add selected track to Queue"),
                ("f", "Toggle Favorite (★)"),
                ("1 - 5", "Tabs: Tracks|Artists|Albums|Favs|Queue"),
                ("v", "Toggle Studio (Cover & Visualizer) / Library"),
                ("l", "In Studio: Toggle Visualizer / Synced Lyrics"),
                ("Space", "Play / Pause"),
                ("h / Right", "Seek -5s / +5s"),
                ("n / b", "Next / Previous track"),
                ("+ / -", "Volume up / down"),
                ("/", "Search library"),
                ("q", "Quit")
            ]
            for idx, (k, d) in enumerate(shortcuts[:modal_h - 5]):
                line = f" {k:<12} : {d}"
                safe_addstr(self.stdscr, start_y + 3 + idx, start_x + 3, line[:modal_w - 6], curses.color_pair(PAIR_MODAL))

            footer = " [ESC/Enter] Back "
            safe_addstr(self.stdscr, start_y + modal_h - 2, start_x + (modal_w - len(footer)) // 2, footer, curses.color_pair(PAIR_MODAL_TITLE))

def main():
    music_dir = None
    if len(sys.argv) > 1:
        music_dir = sys.argv[1]

    curses.wrapper(lambda stdscr: PnutApp(stdscr, music_dir).run())

if __name__ == "__main__":
    main()
