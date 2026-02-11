#!/usr/bin/env python3
"""Fix YAML anchor issues in Rebellion era pack locations.yaml."""

from pathlib import Path

locations_file = Path(__file__).parent.parent / "data" / "static" / "era_packs" / "rebellion" / "locations.yaml"

print(f"Reading {locations_file}")
with open(locations_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")

# Find all lines with *id002 references
fixes = []
for i, line in enumerate(lines, start=1):
    if '*id002' in line:
        fixes.append(i)
        print(f"  Line {i}: {line.rstrip()}")

print(f"\nFound {len(fixes)} alias references to *id002")
print("These need to be replaced with empty arrays: []")

# Replace all *id002 with []
modified_lines = []
for line in lines:
    if '*id002' in line:
        # Replace "access_points: *id002" with "access_points: []"
        line = line.replace('*id002', '[]')
    modified_lines.append(line)

# Write back
backup_file = locations_file.with_suffix('.yaml.bak')
print(f"\nBacking up to {backup_file.name}")
with open(backup_file, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"Writing fixed version to {locations_file.name}")
with open(locations_file, 'w', encoding='utf-8') as f:
    f.writelines(modified_lines)

print("✓ Done! Fixed all *id002 references to []")
