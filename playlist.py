import os
import json
import random
from metadata_parser import extract_track_info

SUPPORTED_EXTENSIONS = (
    # Lossless & Hi-Res Formats
    ".flac", ".wav", ".alac", ".aiff", ".aif", ".ape", ".wv", ".dsf", ".dff", ".mka",
    # Modern & Compressed Formats
    ".ogg", ".opus", ".mp3", ".m4a", ".aac", ".wma"
)

FAVORITES_FILE = os.path.expanduser("~/.config/pnut/favorites.json")
CONFIG_FILE = os.path.expanduser("~/.config/pnut/config.json")

class Track:
    def __init__(self, filepath, info=None):
        self.path = os.path.abspath(filepath)
        self.filename = os.path.basename(filepath)
        if info is None:
            info = extract_track_info(self.path)
        self.title = info.get("title", self.filename)
        self.artist = info.get("artist", "Unknown Artist")
        self.album = info.get("album", "Unknown Album")
        self.track_num = info.get("track_num", 0)
        self.date = info.get("date", "")
        self.embedded_lyrics = info.get("lyrics", "")
        self.display_name = f"{self.artist} - {self.title}"

    def __repr__(self):
        return f"<Track: {self.artist} - {self.title}>"

class LibraryManager:
    VIEW_TRACKS = "tracks"
    VIEW_ARTISTS = "artists"
    VIEW_ALBUMS = "albums"
    VIEW_FAVORITES = "favorites"
    VIEW_QUEUE = "queue"

    def __init__(self, root_dir=None):
        self.root_dir = root_dir or self._find_default_dir()
        self.all_tracks = []
        self.artists_map = {}
        self.albums_map = {}

        self.current_view = self.VIEW_TRACKS
        self.filter_artist = None
        self.filter_album = None
        self.search_query = ""

        # Playback flow state
        self.current_track_path = None
        self.active_playlist = []
        self.playlist_index = -1

        # Flow conveniences: Shuffle, Repeat, Queue, Favorites
        self.shuffle = False
        self.repeat_mode = "off"
        self.queue = []
        self.favorites = set()
        self._load_favorites()

        self.scan_directory(self.root_dir)

    def _find_default_dir(self):
        # 1. Kaydedilmiş müzik klasörü tercihi var mı?
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                saved_dir = cfg.get("music_dir")
                if saved_dir and os.path.isdir(os.path.expanduser(saved_dir)):
                    return os.path.abspath(os.path.expanduser(saved_dir))
            except Exception:
                pass

        # 2. Proje içi ./music klasörü
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_music = os.path.join(base_dir, "music")
        if os.path.isdir(project_music):
            # Dosya var mı kontrol et
            for root, _, files in os.walk(project_music):
                if any(f.lower().endswith(SUPPORTED_EXTENSIONS) for f in files):
                    return project_music

        # 3. Sistem müzik klasörleri
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, "Music"),
            os.path.join(home, "Müzik"),
            project_music,
            os.path.join(home, "Downloads"),
            os.path.join(home, "İndirilenler"),
            os.getcwd(),
        ]
        for c in candidates:
            if os.path.isdir(c):
                for root, _, files in os.walk(c):
                    if any(f.lower().endswith(SUPPORTED_EXTENSIONS) for f in files):
                        return c

        return project_music if os.path.isdir(project_music) else os.getcwd()

    def set_music_directory(self, new_dir):
        """
        Müzik klasörünü değiştirir, yeniden tarar ve tercihi kaydeder.
        """
        new_path = os.path.abspath(os.path.expanduser(new_dir))
        if not os.path.isdir(new_path):
            return False, f"Directory not found: {new_path}"

        self.root_dir = new_path
        self.scan_directory(self.root_dir)

        # Tercihi ~/.config/pnut/config.json dosyasına kaydet
        try:
            cfg = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["music_dir"] = self.root_dir
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return True, self.root_dir

    def _load_favorites(self):
        if os.path.exists(FAVORITES_FILE):
            try:
                with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.favorites = set(data.get("favorites", []))
            except Exception:
                self.favorites = set()

    def _save_favorites(self):
        os.makedirs(os.path.dirname(FAVORITES_FILE), exist_ok=True)
        try:
            with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
                json.dump({"favorites": list(self.favorites)}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def toggle_favorite(self, track):
        if not track:
            return False
        if track.path in self.favorites:
            self.favorites.remove(track.path)
            res = False
        else:
            self.favorites.add(track.path)
            res = True
        self._save_favorites()
        return res

    def is_favorite(self, track):
        return track and track.path in self.favorites

    def add_to_queue(self, track):
        if track:
            self.queue.append(track)
            return len(self.queue)
        return 0

    def remove_from_queue(self, index):
        if 0 <= index < len(self.queue):
            removed = self.queue.pop(index)
            return removed
        return None

    def clear_queue(self):
        self.queue = []

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        return self.shuffle

    def cycle_repeat(self):
        modes = ["off", "all", "single"]
        curr_idx = modes.index(self.repeat_mode)
        self.repeat_mode = modes[(curr_idx + 1) % len(modes)]
        return self.repeat_mode

    def scan_directory(self, target_dir):
        self.root_dir = os.path.abspath(target_dir)
        self.all_tracks = []
        self.artists_map = {}
        self.albums_map = {}

        discovered_paths = []
        if os.path.isdir(self.root_dir):
            for root, _, files in os.walk(self.root_dir):
                for f in sorted(files):
                    if f.lower().endswith(SUPPORTED_EXTENSIONS):
                        discovered_paths.append(os.path.join(root, f))
        elif os.path.isfile(self.root_dir) and self.root_dir.lower().endswith(SUPPORTED_EXTENSIONS):
            discovered_paths.append(self.root_dir)

        for p in discovered_paths:
            info = extract_track_info(p)
            track = Track(p, info)
            self.all_tracks.append(track)

            art = track.artist
            if art not in self.artists_map:
                self.artists_map[art] = []
            self.artists_map[art].append(track)

            alb_key = (track.album, track.artist)
            if alb_key not in self.albums_map:
                self.albums_map[alb_key] = {
                    "name": track.album,
                    "artist": track.artist,
                    "date": track.date,
                    "tracks": []
                }
            self.albums_map[alb_key]["tracks"].append(track)

        for alb in self.albums_map.values():
            alb["tracks"].sort(key=lambda t: (t.track_num if t.track_num > 0 else 999, t.title.lower()))

        self.all_tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower(), t.track_num, t.title.lower()))

        self.update_active_playlist()
        if self.active_playlist and self.playlist_index == -1:
            self.playlist_index = 0

    def update_active_playlist(self):
        tracks = self.all_tracks

        if self.filter_artist:
            tracks = [t for t in tracks if t.artist.lower() == self.filter_artist.lower()]
        elif self.filter_album:
            alb_name, alb_artist = self.filter_album
            tracks = [t for t in tracks if t.album.lower() == alb_name.lower() and (not alb_artist or t.artist.lower() == alb_artist.lower())]

        if self.search_query:
            q = self.search_query.strip().lower()
            if q.startswith("a:"):
                val = q[2:].strip()
                tracks = [t for t in tracks if val in t.artist.lower()]
            elif q.startswith("al:"):
                val = q[3:].strip()
                tracks = [t for t in tracks if val in t.album.lower()]
            elif q.startswith("t:"):
                val = q[2:].strip()
                tracks = [t for t in tracks if val in t.title.lower()]
            else:
                tracks = [t for t in tracks if q in t.title.lower() or q in t.artist.lower() or q in t.album.lower()]

        self.active_playlist = tracks

    def get_view_items(self):
        if self.current_view == self.VIEW_ARTISTS:
            items = []
            q = self.search_query.lower()
            for art in sorted(self.artists_map.keys(), key=lambda s: s.lower()):
                if not q or q in art.lower():
                    items.append({
                        "type": "artist",
                        "name": art,
                        "count": len(self.artists_map[art])
                    })
            return items

        elif self.current_view == self.VIEW_ALBUMS:
            items = []
            q = self.search_query.lower()
            sorted_keys = sorted(self.albums_map.keys(), key=lambda k: (k[1].lower(), k[0].lower()))
            for key in sorted_keys:
                alb = self.albums_map[key]
                match_str = f"{alb['name']} {alb['artist']}".lower()
                if not q or q in match_str:
                    items.append({
                        "type": "album",
                        "name": alb["name"],
                        "artist": alb["artist"],
                        "date": alb["date"],
                        "count": len(alb["tracks"]),
                        "key": key
                    })
            return items

        elif self.current_view == self.VIEW_FAVORITES:
            fav_tracks = [t for t in self.all_tracks if t.path in self.favorites]
            if self.search_query:
                q = self.search_query.lower()
                fav_tracks = [t for t in fav_tracks if q in t.title.lower() or q in t.artist.lower()]
            return fav_tracks

        elif self.current_view == self.VIEW_QUEUE:
            return list(self.queue)

        else:
            self.update_active_playlist()
            return self.active_playlist

    def filter_by_artist(self, artist_name):
        self.filter_artist = artist_name
        self.filter_album = None
        self.current_view = self.VIEW_TRACKS
        self.update_active_playlist()

    def filter_by_album(self, album_key):
        self.filter_album = album_key
        self.filter_artist = None
        self.current_view = self.VIEW_TRACKS
        self.update_active_playlist()

    def clear_filters(self):
        self.filter_artist = None
        self.filter_album = None
        self.search_query = ""
        self.update_active_playlist()

    def get_current_track(self):
        if self.current_track_path:
            for t in self.all_tracks:
                if t.path == self.current_track_path:
                    return t
        if self.active_playlist and 0 <= self.playlist_index < len(self.active_playlist):
            return self.active_playlist[self.playlist_index]
        return None

    def set_current_track(self, track):
        if not track:
            return
        self.current_track_path = track.path
        for idx, t in enumerate(self.active_playlist):
            if t.path == track.path:
                self.playlist_index = idx
                return

    def get_next_track(self, is_auto_end=False):
        if not self.all_tracks:
            return None

        if is_auto_end and self.repeat_mode == "single":
            curr = self.get_current_track()
            if curr:
                return curr

        if self.queue:
            next_t = self.queue.pop(0)
            self.current_track_path = next_t.path
            return next_t

        playlist = self.active_playlist or self.all_tracks
        if not playlist:
            return None

        if self.shuffle:
            if len(playlist) > 1:
                candidates = [t for t in playlist if t.path != self.current_track_path]
                next_t = random.choice(candidates)
            else:
                next_t = playlist[0]
            self.set_current_track(next_t)
            return next_t

        if self.playlist_index >= len(playlist) - 1:
            if self.repeat_mode == "all" or not is_auto_end:
                self.playlist_index = 0
            else:
                return None
        else:
            self.playlist_index += 1

        next_t = playlist[self.playlist_index]
        self.current_track_path = next_t.path
        return next_t

    def get_prev_track(self):
        playlist = self.active_playlist or self.all_tracks
        if not playlist:
            return None

        if self.playlist_index <= 0:
            self.playlist_index = len(playlist) - 1
        else:
            self.playlist_index -= 1

        prev_t = playlist[self.playlist_index]
        self.current_track_path = prev_t.path
        return prev_t

PlaylistManager = LibraryManager
