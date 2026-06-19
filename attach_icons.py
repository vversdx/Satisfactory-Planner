#!/usr/bin/env python3
"""
Attach icons to Items by matching ClassName to filenames.

Usage:
    python attach_icons.py path/to/icons/folder

Icons should be named like: Desc_IronPlate_C_256.png
The script matches Item.name to the original ClassName stored in icon field.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.core.files import File
from planner.models import Item

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/icons/folder")
        sys.exit(1)

    icons_dir = Path(sys.argv[1])
    if not icons_dir.exists():
        print(f"Folder not found: {icons_dir}")
        sys.exit(1)

    # Build lookup: lowercase classname -> filepath
    icon_files = {}
    for f in icons_dir.iterdir():
        if not f.is_file():
            continue
        name = f.stem.lower().replace('-', '_').replace('_256', '').replace('_64', '')
        icon_files[name] = f

    print(f"Found {len(icon_files)} icon files")

    updated = 0
    skipped = 0

    for item in Item.objects.all():
        # Extract classname from icon path: items/Desc_IronPlate_C.png -> Desc_IronPlate_C
        icon_path = item.icon.name if item.icon else ''
        classname = Path(icon_path).stem  # Desc_IronPlate_C
        classname_lower = classname.lower().replace('-', '_')

        if classname_lower in icon_files:
            filepath = icon_files[classname_lower]
            with open(filepath, 'rb') as f:
                item.icon.save(f'{classname}.png', File(f), save=True)
            updated += 1
        else:
            skipped += 1

    print(f"Updated: {updated}")
    print(f"Skipped (no icon found): {skipped}")

if __name__ == '__main__':
    main()
