import os
import shutil
import struct
import subprocess
import hashlib
from PIL import Image

CACHE_DIR = "/tmp/flac_player_covers"

# Varsayılan retro ASCII plak / vinyl çizimi (Kapak bulunamadığında)
DEFAULT_VINYL_ART = [
    r"       .---.       ",
    r"     /  ...  \     ",
    r"    |  ( @ )  |    ",
    r"     \  ...  /     ",
    r"       '---'       ",
    r"   [ NO COVER ]    "
]

class CoverArtManager:
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.chafa_path = shutil.which("chafa")

    def get_cover_image_path(self, audio_path):
        """
        FLAC veya diğer ses dosyalarından albüm kapağını çıkarır ve cache yolunu döndürür.
        """
        if not audio_path or not os.path.exists(audio_path):
            return None

        # Hash ile benzersiz dosya adı
        file_hash = hashlib.md5(audio_path.encode("utf-8")).hexdigest()
        cached_img = os.path.join(CACHE_DIR, f"{file_hash}.jpg")

        if os.path.exists(cached_img):
            return cached_img

        # 1. FLAC PICTURE bloğunu doğrudan ayrıştır
        if audio_path.lower().endswith(".flac"):
            data = self._extract_flac_picture_block(audio_path)
            if data:
                try:
                    with open(cached_img, "wb") as f:
                        f.write(data)
                    return cached_img
                except Exception:
                    pass

        # 2. ffmpeg ile ses dosyasından görsel akışını çıkar
        try:
            cmd = [
                "ffmpeg", "-y", "-v", "quiet",
                "-i", audio_path,
                "-an", "-vcodec", "copy",
                cached_img
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.0)
            if res.returncode == 0 and os.path.exists(cached_img) and os.path.getsize(cached_img) > 0:
                return cached_img
        except Exception:
            pass

        # 3. Şarkının bulunduğu klasördeki cover.jpg, folder.jpg vb. görsellere bak
        parent = os.path.dirname(audio_path)
        candidates = ["cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "front.png", "album.jpg"]
        for c in candidates:
            p = os.path.join(parent, c)
            if os.path.exists(p):
                return p

        return None

    def _extract_flac_picture_block(self, flac_path):
        """
        Saf Python ile FLAC METADATA_BLOCK_PICTURE (block_type 6) ayrıştırma.
        """
        try:
            with open(flac_path, "rb") as f:
                if f.read(4) != b"fLaC":
                    return None
                while True:
                    hdr = f.read(4)
                    if len(hdr) < 4:
                        break
                    is_last = (hdr[0] & 0x80) != 0
                    btype = hdr[0] & 0x7F
                    length = struct.unpack(">I", b"\x00" + hdr[1:4])[0]

                    if btype == 6:  # PICTURE
                        block_data = f.read(length)
                        # Picture type (4B) + MIME len (4B)
                        mime_len = struct.unpack(">I", block_data[4:8])[0]
                        offset = 8 + mime_len
                        # Desc len (4B)
                        desc_len = struct.unpack(">I", block_data[offset:offset+4])[0]
                        offset += 4 + desc_len + 16  # width(4) + height(4) + depth(4) + colors(4)
                        data_len = struct.unpack(">I", block_data[offset:offset+4])[0]
                        offset += 4
                        return block_data[offset:offset+data_len]
                    else:
                        f.seek(length, 1)

                    if is_last:
                        break
        except Exception:
            pass
        return None

    def render_cover_ascii(self, img_path, width, height):
        """
        Pillow kullanarak curses uyumlu saf ASCII/Block karakter sanatı üretir.
        """
        if not img_path or not os.path.exists(img_path):
            return DEFAULT_VINYL_ART

        try:
            with Image.open(img_path) as img:
                img = img.convert("L")  # Grayscale
                # Terminal karakterleri dikeyde 2 kat uzun olduğundan oranı ayarla
                target_w = max(10, width)
                target_h = max(5, height)
                img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)

                ascii_chars = [" ", "░", "▒", "▓", "█"]
                lines = []
                for y in range(target_h):
                    line_chars = []
                    for x in range(target_w):
                        val = img.getpixel((x, y))
                        char_idx = int(val / 256 * len(ascii_chars))
                        char_idx = min(len(ascii_chars) - 1, max(0, char_idx))
                        line_chars.append(ascii_chars[char_idx])
                    lines.append("".join(line_chars))
                return lines
        except Exception:
            return DEFAULT_VINYL_ART

    def render_cover_chafa(self, img_path, width, height):
        """
        Eğer chafa kuruluysa yüksek kaliteli sembollerle renkli terminal çıktısı alır.
        """
        if not self.chafa_path or not img_path or not os.path.exists(img_path):
            return None

        try:
            cmd = [
                self.chafa_path,
                f"--size={width}x{height}",
                "--format=symbols",
                "--colors=256",
                img_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=1.5)
            if res.returncode == 0 and res.stdout:
                return res.stdout.splitlines()
        except Exception:
            pass
        return None
