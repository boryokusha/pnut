import os
import json
import re
import struct
import subprocess

def parse_flac_vorbis_comments(filepath):
    """
    Saf Python ile harici kütüphane olmadan FLAC Vorbis Comment bloklarını okur.
    """
    meta = {}
    try:
        with open(filepath, "rb") as f:
            if f.read(4) != b"fLaC":
                return meta

            while True:
                header = f.read(4)
                if len(header) < 4:
                    break

                is_last = (header[0] & 0x80) != 0
                block_type = header[0] & 0x7F
                length = struct.unpack(">I", b"\x00" + header[1:4])[0]

                if block_type == 4:  # VORBIS_COMMENT
                    vendor_len = struct.unpack("<I", f.read(4))[0]
                    f.read(vendor_len)
                    num_comments = struct.unpack("<I", f.read(4))[0]

                    for _ in range(num_comments):
                        c_len = struct.unpack("<I", f.read(4))[0]
                        c_bytes = f.read(c_len)
                        c_str = c_bytes.decode("utf-8", errors="ignore")
                        if "=" in c_str:
                            k, v = c_str.split("=", 1)
                            meta[k.upper()] = v.strip()
                    break
                else:
                    f.seek(length, 1)

                if is_last:
                    break
    except Exception:
        pass
    return meta

def parse_ffprobe_metadata(filepath):
    """
    Tüm ses formatları (FLAC, MP3, OGG, OPUS, M4A, DSF, APE, WV vb.) için ffprobe çıktısını okur.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            filepath
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=1.5)
        if res.returncode == 0:
            data = json.loads(res.stdout)
            tags = data.get("format", {}).get("tags", {})
            return {k.upper(): str(v).strip() for k, v in tags.items()}
    except Exception:
        pass
    return {}

def extract_track_info(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    raw_meta = {}

    if ext == ".flac":
        raw_meta = parse_flac_vorbis_comments(filepath)
    if not raw_meta:
        raw_meta = parse_ffprobe_metadata(filepath)

    artist = raw_meta.get("ARTIST") or raw_meta.get("ALBUMARTIST") or raw_meta.get("PERFORMER")
    album = raw_meta.get("ALBUM")
    title = raw_meta.get("TITLE")
    date = raw_meta.get("DATE") or raw_meta.get("YEAR")
    track_num_raw = raw_meta.get("TRACKNUMBER") or raw_meta.get("TRACK") or "0"

    # Gömülü şarkı sözü
    lyrics = (
        raw_meta.get("LYRICS") or
        raw_meta.get("UNSYNCEDLYRICS") or
        raw_meta.get("SYNCEDLYRICS") or
        raw_meta.get("DESCRIPTION") or
        ""
    )

    try:
        track_num = int(str(track_num_raw).split("/")[0])
    except (ValueError, TypeError):
        track_num = 0

    filename = os.path.splitext(os.path.basename(filepath))[0]
    parent_dir = os.path.basename(os.path.dirname(filepath))
    grandparent_dir = os.path.basename(os.path.dirname(os.path.dirname(filepath)))

    if not title:
        if " - " in filename:
            parts = filename.split(" - ", 1)
            guessed_artist = parts[0].strip()
            guessed_title = parts[1].strip()
            m = re.match(r"^(\d+)[\.\s-]+(.*)$", guessed_title)
            if m:
                guessed_title = m.group(2).strip()
            if not artist and not guessed_artist.isdigit():
                artist = guessed_artist
            title = guessed_title
        else:
            m = re.match(r"^(\d+)[\.\s-]+(.*)$", filename)
            if m:
                if track_num == 0:
                    try:
                        track_num = int(m.group(1))
                    except ValueError:
                        pass
                title = m.group(2).strip()
            else:
                title = filename

    if not artist:
        if grandparent_dir and grandparent_dir.lower() not in ("indirilenler", "downloads", "müzik", "music", "belgeler", "documents", ""):
            artist = grandparent_dir
        elif parent_dir and parent_dir.lower() not in ("indirilenler", "downloads", "müzik", "music", "belgeler", "documents", ""):
            artist = parent_dir
        else:
            artist = "Bilinmeyen Sanatçı"

    if not album:
        if parent_dir and parent_dir.lower() not in ("indirilenler", "downloads", "müzik", "music", "belgeler", "documents", ""):
            album = parent_dir
        else:
            album = "Tekliler & Bilinmeyen Albüm"

    return {
        "title": title or filename,
        "artist": artist.strip(),
        "album": album.strip(),
        "track_num": track_num,
        "date": date or "",
        "lyrics": lyrics.strip()
    }
