import json
import os
import socket
import subprocess
import time

class MPVAudioEngine:
    def __init__(self, socket_path="/tmp/flac_player_mpv.sock"):
        self.socket_path = socket_path
        self.process = None
        self._sock = None
        self.current_file = None
        self.volume = 100
        self.start_process()

    def start_process(self):
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass

        cmd = [
            "mpv",
            "--no-video",
            "--idle=yes",
            f"--input-ipc-server={self.socket_path}",
            "--audio-display=no",
            "--gapless-audio=yes",
            "--ao=pipewire,pulse,alsa",
            "--really-quiet"
        ]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        for _ in range(20):
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.1)

    def _send_command(self, cmd_data):
        if not os.path.exists(self.socket_path):
            return None

        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            sock.connect(self.socket_path)
            msg = json.dumps(cmd_data) + "\n"
            sock.sendall(msg.encode("utf-8"))

            response_data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in chunk:
                    break

            sock.close()
            for line in response_data.decode("utf-8", errors="ignore").splitlines():
                if line.strip():
                    try:
                        parsed = json.loads(line)
                        if "data" in parsed or "error" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        continue
            return None
        except (socket.error, socket.timeout):
            return None

    def load_file(self, filepath):
        self.current_file = filepath
        cmd = {"command": ["loadfile", os.path.abspath(filepath), "replace"]}
        return self._send_command(cmd)

    def toggle_pause(self):
        cmd = {"command": ["cycle", "pause"]}
        return self._send_command(cmd)

    def pause(self):
        cmd = {"command": ["set_property", "pause", True]}
        return self._send_command(cmd)

    def resume(self):
        cmd = {"command": ["set_property", "pause", False]}
        return self._send_command(cmd)

    def seek(self, seconds):
        cmd = {"command": ["seek", seconds, "relative"]}
        return self._send_command(cmd)

    def set_volume(self, val):
        val = max(0, min(130, val))
        self.volume = val
        cmd = {"command": ["set_property", "volume", val]}
        return self._send_command(cmd)

    def change_volume(self, delta):
        self.volume = max(0, min(130, self.volume + delta))
        return self.set_volume(self.volume)

    def apply_lavfi(self, lavfi_str):
        af_val = f"lavfi=[{lavfi_str}]" if lavfi_str else ""
        cmd = {"command": ["set_property", "af", af_val]}
        return self._send_command(cmd)

    def get_property(self, prop_name):
        cmd = {"command": ["get_property", prop_name]}
        res = self._send_command(cmd)
        if res and res.get("error") == "success":
            return res.get("data")
        return None

    def get_status(self):
        time_pos = self.get_property("time-pos") or 0.0
        duration = self.get_property("duration") or 0.0
        is_paused = self.get_property("pause")
        vol = self.get_property("volume")
        eof = self.get_property("eof-reached")
        idle = self.get_property("idle-active")

        if vol is not None:
            self.volume = vol

        meta = self.get_property("metadata") or {}
        audio_params = self.get_property("audio-params") or {}

        return {
            "time_pos": float(time_pos),
            "duration": float(duration),
            "is_paused": bool(is_paused),
            "volume": int(self.volume),
            "eof_reached": bool(eof),
            "is_idle": bool(idle),
            "artist": meta.get("artist") or meta.get("ARTIST") or "",
            "title": meta.get("title") or meta.get("TITLE") or "",
            "album": meta.get("album") or meta.get("ALBUM") or "",
            "samplerate": audio_params.get("samplerate"),
            "channels": audio_params.get("channels"),
            "format": audio_params.get("format"),
            "file": self.current_file
        }

    def quit(self):
        try:
            self._send_command({"command": ["quit"]})
        except Exception:
            pass
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=0.8)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except OSError:
                pass
