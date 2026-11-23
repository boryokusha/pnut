import os
import shutil
import subprocess
import threading
import time
import numpy as np

BAR_CHARS = [" ", " ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]

class AudioVisualizer:
    def __init__(self, num_bars=24):
        self.num_bars = num_bars
        self.bars = [0.0] * self.num_bars
        self.running = False
        self.thread = None
        self.has_cava = shutil.which("cava") is not None
        self.process = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None

    def get_bars(self):
        return list(self.bars)

    def _run_loop(self):
        # Sistemde cava varsa öncelikli olarak cava'yı kullan
        if self.has_cava:
            if self._run_cava():
                return
        # Cava yoksa PipeWire / NumPy analiz motoru çalışır
        self._run_native_pipewire()

    def _run_cava(self):
        config_path = "/tmp/flac_player_cava.conf"
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(f"""[general]
bars = {self.num_bars}
framerate = 30
autosens = 1

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 8
bar_delimiter = 59
""")
            self.process = subprocess.Popen(
                ["cava", "-p", config_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
            while self.running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break
                parts = line.strip().split(";")
                vals = []
                for p in parts:
                    if p.isdigit():
                        vals.append(min(8, int(p)) / 8.0)
                if len(vals) >= self.num_bars:
                    self.bars = vals[:self.num_bars]
            return True
        except Exception:
            return False

    def _run_native_pipewire(self):
        sample_rate = 22050
        chunk_size = 1024
        cmd = ["parec", "--format=s16le", f"--rate={sample_rate}", "--channels=1"]

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=chunk_size * 2
            )
        except Exception:
            self.process = None

        decay = 0.72
        freq_bins = np.logspace(np.log10(30), np.log10(8000), self.num_bars + 1)

        while self.running:
            if self.process and self.process.poll() is None:
                try:
                    raw_data = self.process.stdout.read(chunk_size * 2)
                    if len(raw_data) == chunk_size * 2:
                        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                        fft_vals = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
                        freqs = np.fft.rfftfreq(len(samples), 1.0 / sample_rate)

                        new_bars = []
                        for i in range(self.num_bars):
                            idx = np.where((freqs >= freq_bins[i]) & (freqs < freq_bins[i + 1]))[0]
                            if len(idx) > 0:
                                val = np.mean(fft_vals[idx]) * (1.0 + (i / self.num_bars) * 1.5)
                                norm_val = min(1.0, max(0.0, val * 2.2))
                            else:
                                norm_val = 0.0
                            curr = self.bars[i] if i < len(self.bars) else 0.0
                            smooth = max(norm_val, curr * decay)
                            new_bars.append(smooth)

                        self.bars = new_bars
                        time.sleep(0.025)
                        continue
                except Exception:
                    pass

            self.bars = [max(0.0, b * decay) for b in self.bars]
            time.sleep(0.04)

def render_vertical_cava_column(height, val):
    total_steps = height * 8
    active_steps = int(round(val * total_steps))
    col = []
    for row in range(height):
        level = (height - 1 - row) * 8
        if active_steps >= level + 8:
            col.append("█")
        elif active_steps <= level:
            col.append(" ")
        else:
            fraction = active_steps - level
            col.append(BAR_CHARS[fraction])
    return col
