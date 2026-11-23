import json
import os
import re
import glob

class EQManager:
    def __init__(self, presets_path=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.presets_path = presets_path or os.path.join(base_dir, "eq_presets.json")
        self.user_eq_dir = os.path.expanduser("~/.config/pnut/eq")
        self.legacy_user_eq_dir = os.path.expanduser("~/.config/flac_player/eq")
        os.makedirs(self.user_eq_dir, exist_ok=True)

        self.presets = []
        self.active_index = 0
        self.is_enabled = True
        self.load_all_presets()

    def load_all_presets(self):
        all_presets = []
        seen_ids = set()

        if os.path.exists(self.presets_path):
            try:
                with open(self.presets_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for p in data.get("presets", []):
                        pid = p.get("id")
                        if pid and pid not in seen_ids:
                            all_presets.append(p)
                            seen_ids.add(pid)
            except Exception:
                pass

        dirs = [self.legacy_user_eq_dir, self.user_eq_dir]
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for fpath in sorted(glob.glob(os.path.join(d, "*.json"))):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict) and "filters" in data:
                            pid = data.get("id") or os.path.splitext(os.path.basename(fpath))[0]
                            data["id"] = pid
                            data["is_user_custom"] = True
                            if pid not in seen_ids:
                                all_presets.append(data)
                                seen_ids.add(pid)
                except Exception:
                    continue

            for fpath in sorted(glob.glob(os.path.join(d, "*.txt"))):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    fname = os.path.splitext(os.path.basename(fpath))[0]
                    pid = "user_" + re.sub(r'[^a-zA-Z0-9_]', '_', fname.lower())
                    if pid not in seen_ids:
                        p = self._parse_autoeq_text(content, fname.replace("_", " ").title(), "User AutoEQ Profile")
                        p["id"] = pid
                        p["is_user_custom"] = True
                        p["file_path"] = fpath
                        all_presets.append(p)
                        seen_ids.add(pid)
                except Exception:
                    continue

        if not all_presets:
            all_presets = [{
                "id": "flat",
                "name": "Direct / Bit-Perfect",
                "description": "Flat sound without filters",
                "preamp_db": 0.0,
                "filters": []
            }]

        self.presets = all_presets

    def save_user_profile(self, name, preamp_db, filters, description="Custom IEM Profile"):
        pid = "custom_" + re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
        profile_data = {
            "id": pid,
            "name": name,
            "description": description,
            "preamp_db": float(preamp_db),
            "filters": filters,
            "is_user_custom": True
        }
        dest_path = os.path.join(self.user_eq_dir, f"{pid}.json")
        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)
            self.load_all_presets()
            for idx, p in enumerate(self.presets):
                if p["id"] == pid:
                    self.active_index = idx
                    break
            return True, dest_path
        except Exception as e:
            return False, str(e)

    def delete_user_profile(self, preset_id):
        deleted = False
        for d in [self.user_eq_dir, self.legacy_user_eq_dir]:
            json_path = os.path.join(d, f"{preset_id}.json")
            if os.path.exists(json_path):
                try:
                    os.remove(json_path)
                    deleted = True
                except Exception:
                    pass
        if deleted:
            self.load_all_presets()
            self.active_index = max(0, min(self.active_index, len(self.presets) - 1))
        return deleted

    def get_active_preset(self):
        if not self.presets:
            return None
        return self.presets[self.active_index % len(self.presets)]

    def next_preset(self):
        if self.presets:
            self.active_index = (self.active_index + 1) % len(self.presets)
            return self.get_active_preset()
        return None

    def prev_preset(self):
        if self.presets:
            self.active_index = (self.active_index - 1 + len(self.presets)) % len(self.presets)
            return self.get_active_preset()
        return None

    def toggle(self):
        self.is_enabled = not self.is_enabled
        return self.is_enabled

    def build_lavfi_string(self):
        if not self.is_enabled:
            return ""

        preset = self.get_active_preset()
        if not preset:
            return ""

        filters = preset.get("filters", [])
        preamp = preset.get("preamp_db", 0.0)

        if not filters and abs(preamp) < 0.01:
            return ""

        lavfi_parts = []
        if abs(preamp) >= 0.01:
            lavfi_parts.append(f"volume={preamp:.2f}dB")

        for f in filters:
            ftype = f.get("type", "peaking").lower()
            freq = f.get("freq", 1000)
            q = f.get("q", 1.0)
            gain = f.get("gain", 0.0)

            if abs(gain) < 0.01:
                continue

            if ftype in ("lowshelf", "lsc"):
                lavfi_parts.append(f"lowshelf=f={freq}:t=q:w={q:.2f}:g={gain:.2f}")
            elif ftype in ("highshelf", "hsc"):
                lavfi_parts.append(f"highshelf=f={freq}:t=q:w={q:.2f}:g={gain:.2f}")
            else:
                lavfi_parts.append(f"equalizer=f={freq}:t=q:w={q:.2f}:g={gain:.2f}")

        if not lavfi_parts:
            return ""

        return ",".join(lavfi_parts)

    def _parse_autoeq_text(self, text, name, description):
        preamp_db = 0.0
        filters = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            preamp_match = re.match(r"Preamp:\s*([+-]?\d+(?:\.\d+)?)\s*dB", line, re.IGNORECASE)
            if preamp_match:
                preamp_db = float(preamp_match.group(1))
                continue

            filter_match = re.match(
                r"Filter\s+\d+:\s*(ON|OFF)\s+([A-Za-z]+)\s+Fc\s+(\d+(?:\.\d+)?)\s*Hz\s+Gain\s+([+-]?\d+(?:\.\d+)?)\s*dB\s+Q\s+(\d+(?:\.\d+)?)",
                line,
                re.IGNORECASE
            )
            if filter_match:
                status, ftype_raw, freq_str, gain_str, q_str = filter_match.groups()
                if status.upper() == "OFF":
                    continue
                ftype_raw = ftype_raw.upper()
                if ftype_raw in ("LSC", "LOWSHELF"):
                    ftype = "lowshelf"
                elif ftype_raw in ("HSC", "HIGHSHELF"):
                    ftype = "highshelf"
                else:
                    ftype = "peaking"

                filters.append({
                    "type": ftype,
                    "freq": float(freq_str),
                    "q": float(q_str),
                    "gain": float(gain_str)
                })

        return {
            "id": re.sub(r'[^a-zA-Z0-9_]', '_', name.lower()),
            "name": name,
            "description": description,
            "preamp_db": preamp_db,
            "filters": filters
        }

    def import_autoeq_text(self, text, name, description="Custom AutoEQ Profile"):
        parsed = self._parse_autoeq_text(text, name, description)
        pid = parsed["id"]
        dest_path = os.path.join(self.user_eq_dir, f"{pid}.json")
        try:
            with open(dest_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, indent=2, ensure_ascii=False)
            self.load_all_presets()
            for idx, p in enumerate(self.presets):
                if p["id"] == pid:
                    return idx
        except Exception:
            pass
        return len(self.presets) - 1
