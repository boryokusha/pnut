#!/usr/bin/env python3
import sys
import os
from eq_manager import EQManager

def main():
    if len(sys.argv) < 3:
        print("🎧 pnut — IEM AutoEQ Profile Importer")
        print("Usage: python import_autoeq.py <autoeq_file.txt> \"Earphone Model Name\" [Description]")
        print("Example: python import_autoeq.py crinacle_waner.txt \"Tangzu Wan'er Custom\" \"Crinacle 711 rig\"")
        print("\nNote: Profiles are stored in ~/.config/pnut/eq/")
        print("Inside pnut, press [s] -> IEM EQ Profiles to select your profile.")
        sys.exit(1)

    filepath = sys.argv[1]
    name = sys.argv[2]
    desc = sys.argv[3] if len(sys.argv) > 3 else "Custom IEM AutoEQ Profile"

    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found!")
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    eq = EQManager()
    idx = eq.import_autoeq_text(content, name, desc)
    preset = eq.presets[idx]
    print(f"✓ Successfully imported: '{preset['name']}'")
    print(f"  Preamp: {preset.get('preamp_db', 0.0)} dB")
    print(f"  Filters Count: {len(preset.get('filters', []))}")
    print(f"  Location: ~/.config/pnut/eq/")
    print(f"  Press [s] inside pnut to activate it!")

if __name__ == "__main__":
    main()
