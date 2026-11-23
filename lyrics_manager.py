import os
import re
import json
import hashlib
import urllib.request
import urllib.parse
import threading

CACHE_DIR = os.path.expanduser("~/.cache/flac_player/lyrics")

class LyricLine:
    def __init__(self, time_sec, text):
        self.time_sec = float(time_sec)
        self.text = text.strip()

    def __repr__(self):
        return f"[{self.time_sec:.2f}] {self.text}"

class LyricsManager:
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.current_track_path = None
        self.is_synced = False
        self.lines = []  # List of LyricLine
        self.is_loading = False
        self.status_text = ""

    def load_lyrics_for_track(self, track, duration=0):
        """
        Şarkı için senkron veya düz şarkı sözlerini arka planda asenkron yükler.
        """
        if not track:
            self.lines = []
            self.is_synced = False
            return

        self.current_track_path = track.path
        self.lines = []
        self.is_synced = False
        self.is_loading = True
        self.status_text = "Sözler aranıyor..."

        thread = threading.Thread(
            target=self._fetch_lyrics_worker,
            args=(track, duration),
            daemon=True
        )
        thread.start()

    def _fetch_lyrics_worker(self, track, duration):
        text = None

        # 1. Yerel .lrc veya .txt dosyası (şarkıyla aynı isimde ve dizinde)
        base_no_ext = os.path.splitext(track.path)[0]
        for ext in (".lrc", ".LRC", ".txt", ".TXT"):
            cand = base_no_ext + ext
            if os.path.exists(cand):
                try:
                    with open(cand, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    break
                except Exception:
                    pass

        # 2. Şarkının içine gömülü metadata (Vorbis/ID3 tag)
        if not text and track.embedded_lyrics:
            text = track.embedded_lyrics

        # 3. Yerel cache (~/.cache/flac_player/lyrics/<hash>.lrc)
        track_hash = hashlib.md5(f"{track.artist}_{track.title}".lower().encode("utf-8")).hexdigest()
        cache_path = os.path.join(CACHE_DIR, f"{track_hash}.lrc")
        if not text and os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception:
                pass

        # 4. Çevrimiçi LRCLIB API (Ücretsiz, Açık Kaynak, API Keysiz)
        if not text and track.artist and track.title and track.artist != "Bilinmeyen Sanatçı":
            text = self._fetch_from_lrclib(track.artist, track.title, track.album, duration, cache_path)

        if text:
            self._parse_lyrics_text(text)
            self.status_text = "Senkron Sözler" if self.is_synced else "Düz Metin Sözler"
        else:
            self.lines = []
            self.is_synced = False
            self.status_text = "Şarkı sözü bulunamadı"

        self.is_loading = False

    def _fetch_from_lrclib(self, artist, title, album, duration, cache_path):
        """
        LRCLIB API'den senkron veya düz sözleri indirir ve cache'e yazar.
        """
        try:
            params = {
                "artist_name": artist,
                "track_name": title
            }
            if album and "Tekliler" not in album and "Bilinmeyen" not in album:
                params["album_name"] = album
            if duration > 10:
                params["duration"] = int(duration)

            url = "https://lrclib.net/api/get?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "FLAC-Terminal-Player/1.0 (https://github.com/)"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    synced = data.get("syncedLyrics")
                    plain = data.get("plainLyrics")
                    chosen = synced or plain
                    if chosen:
                        # Cache'e kaydet
                        try:
                            with open(cache_path, "w", encoding="utf-8") as f:
                                f.write(chosen)
                        except Exception:
                            pass
                        return chosen
        except Exception:
            pass
        return None

    def _parse_lyrics_text(self, text):
        """
        LRC veya düz metin sözleri satırlara ve zaman damgalarına ayrıştırır.
        """
        parsed_lines = []
        has_timestamp = False

        time_pattern = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            matches = list(time_pattern.finditer(line))
            if matches:
                has_timestamp = True
                lyric_text = time_pattern.sub("", line).strip()
                for m in matches:
                    minutes = float(m.group(1))
                    seconds = float(m.group(2))
                    total_sec = minutes * 60 + seconds
                    parsed_lines.append(LyricLine(total_sec, lyric_text))
            else:
                # Düz metin satırı
                parsed_lines.append(LyricLine(-1.0, line))

        if has_timestamp:
            # Senkronize sözleri zamana göre sırala
            self.lines = sorted([l for l in parsed_lines if l.time_sec >= 0], key=lambda x: x.time_sec)
            self.is_synced = True
        else:
            self.lines = parsed_lines
            self.is_synced = False

    def get_current_line_index(self, current_seconds):
        """
        Verilen saniyede hangi satırın aktif olduğunu döndürür.
        """
        if not self.is_synced or not self.lines:
            return -1

        active_idx = 0
        for idx, line in enumerate(self.lines):
            if line.time_sec <= current_seconds:
                active_idx = idx
            else:
                break
        return active_idx

    def get_window(self, current_seconds, window_size=7):
        """
        Ekranda kaydırılarak gösterilecek (önceki, aktif, sonraki) satırları döndürür.
        """
        if not self.lines:
            return [], -1

        if not self.is_synced:
            # Senkron değilse ilk N satırı döndür
            return self.lines[:window_size], -1

        curr_idx = self.get_current_line_index(current_seconds)
        half = window_size // 2

        start_idx = max(0, curr_idx - half)
        end_idx = min(len(self.lines), start_idx + window_size)

        if end_idx - start_idx < window_size and start_idx > 0:
            start_idx = max(0, end_idx - window_size)

        visible_lines = self.lines[start_idx:end_idx]
        local_active_idx = curr_idx - start_idx
        return visible_lines, local_active_idx
